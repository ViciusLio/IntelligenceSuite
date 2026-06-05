"""Pure translation layer — OpenAI ↔ IntelligenceSuite.

Everything in this module is I/O-free and side-effect-free so it can be unit
tested without a network, a running server, or even the settings object
(except :func:`upstream_base_url`, which reads ports from a settings-like
object passed in by the caller).

Responsibilities
----------------
* Map an OpenAI ``model`` field to a concrete IntelligenceSuite module.
* Heuristically route the ``intelligence-suite`` (auto) model to a module.
* Convert an OpenAI chat request into an IntelligenceSuite ``/api/v1/query`` body.
* Convert an IntelligenceSuite ``QueryResponse`` into an OpenAI ``chat.completion``.
* Convert IntelligenceSuite SSE events into OpenAI ``chat.completion.chunk`` SSE.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass


# ── Module registry ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ModuleRoute:
    """A selectable IntelligenceSuite module, surfaced as an OpenAI 'model'."""
    model_id:     str   # OpenAI `model` value, e.g. "code-intelligence"
    display:      str   # friendly label, e.g. "Code Intelligence"
    domain:       str   # IS domain tag: "code" | "doc" | "mentor" | "proposal"
    port_setting: str   # attribute name on settings, e.g. "ci_port"


# The four concrete modules exposed in the OpenWebUI model dropdown.
MODULES: dict[str, ModuleRoute] = {
    "code-intelligence":     ModuleRoute("code-intelligence",     "Code Intelligence",     "code",     "ci_port"),
    "doc-intelligence":      ModuleRoute("doc-intelligence",      "Doc Intelligence",      "doc",      "di_port"),
    "mentor-intelligence":   ModuleRoute("mentor-intelligence",   "Mentor Intelligence",   "mentor",   "mi_port"),
    "proposal-intelligence": ModuleRoute("proposal-intelligence", "Proposal Intelligence", "proposal", "pi_port"),
}

# The fifth, virtual "model": auto-routes to one of the four above.
AUTO_MODEL = "intelligence-suite"

# Default module when the heuristic finds no signal (general document Q&A).
DEFAULT_MODULE = "doc-intelligence"


# ── Auto-routing heuristic (strategy A) ───────────────────────────────────────
# Keyword → module. Order matters only for documentation; scoring counts hits.
# Italian + English triggers, lowercased substring match.

_ROUTE_KEYWORDS: dict[str, list[str]] = {
    "code-intelligence": [
        "funzione", "classe", "metodo", "variabile", "bug", "errore", "eccezione",
        "stacktrace", "stack trace", "import", "endpoint", "api", "refactor",
        "compila", "build", "deploy", "git", "commit", "branch", "test",
        "function", "class", "method", "exception", "code", "codice", "repository",
        "repo", "sql", "query", "yaml", "regex", "parser",
    ],
    "doc-intelligence": [
        "documento", "documenti", "pdf", "report", "relazione", "manuale",
        "contratto", "policy", "procedura", "allegato", "foglio", "excel",
        "tabella", "paragrafo", "capitolo", "sezione", "word", "docx", "xlsx",
        "document", "spreadsheet", "chapter", "page", "pagina",
    ],
    "mentor-intelligence": [
        "onboarding", "inizio", "come inizio", "come parto", "impara", "imparare",
        "formazione", "percorso", "guidami", "principiante", "junior", "tutorial",
        "spiegami da zero", "non so da dove", "mentor", "carriera", "crescita",
        "learn", "learning", "getting started", "ramp up", "new hire",
    ],
    "proposal-intelligence": [
        "gara", "bando", "questionario", "capitolato", "offerta", "rfp", "rfi",
        "proposta", "tender", "requisito di gara", "rispondi alla domanda",
        "compila il questionario", "scheda tecnica", "proposal", "questionnaire",
    ],
}


def route_module(question: str) -> str:
    """Heuristically pick a concrete module id for the auto model.

    Pure keyword scoring: the module with the most distinct keyword hits wins.
    Ties and zero-hit queries fall back to :data:`DEFAULT_MODULE`.
    """
    q = (question or "").lower()
    best_id = DEFAULT_MODULE
    best_score = 0
    for model_id, keywords in _ROUTE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in q)
        if score > best_score:
            best_score = score
            best_id = model_id
    return best_id


def resolve_model(model: str, question: str) -> ModuleRoute:
    """Map an OpenAI ``model`` value to a concrete :class:`ModuleRoute`.

    * A concrete module id → that module.
    * The auto model id → heuristic routing via :func:`route_module`.
    * Anything else → ``KeyError`` (the endpoint turns this into HTTP 404).
    """
    if model in MODULES:
        return MODULES[model]
    if model == AUTO_MODEL:
        return MODULES[route_module(question)]
    raise KeyError(model)


def upstream_base_url(route: ModuleRoute, settings, *, host: str | None = None) -> str:
    """Build the upstream base URL for a module from a settings-like object.

    ``host`` precedence: explicit arg → ``settings.gw_upstream_host`` →
    ``"localhost"``. This lets docker-compose point at service names without
    touching the call sites.
    """
    resolved_host = host or getattr(settings, "gw_upstream_host", None) or "localhost"
    port = getattr(settings, route.port_setting)
    return f"http://{resolved_host}:{port}"


# ── Models listing ────────────────────────────────────────────────────────────

def list_models() -> list[dict]:
    """Return the OpenAI ``/v1/models`` data array (4 modules + auto)."""
    models = [
        {
            "id":       r.model_id,
            "object":   "model",
            "created":  0,
            "owned_by": "intelligence-suite",
            "name":     r.display,  # non-standard courtesy field; UIs may use it
        }
        for r in MODULES.values()
    ]
    models.append({
        "id":       AUTO_MODEL,
        "object":   "model",
        "created":  0,
        "owned_by": "intelligence-suite",
        "name":     "Intelligence Suite (Auto)",
    })
    return models


# ── OpenAI request → IntelligenceSuite request ────────────────────────────────

def _coerce_content(content) -> str:
    """OpenAI content may be a string or a list of parts. Flatten to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts)
    return "" if content is None else str(content)


def split_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Split OpenAI messages into (current question, prior history).

    * ``question`` = content of the LAST user message.
    * ``history``  = all user/assistant turns *before* that message, in order
                     (system messages are dropped — IS supplies its own).
    """
    last_user_idx: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break

    if last_user_idx is None:
        return "", []

    question = _coerce_content(messages[last_user_idx].get("content"))
    history = [
        {"role": m["role"], "content": _coerce_content(m.get("content"))}
        for m in messages[:last_user_idx]
        if m.get("role") in ("user", "assistant")
    ]
    return question, history


def openai_to_is_request(body: dict) -> tuple[ModuleRoute, dict]:
    """Translate an OpenAI chat request into (route, IS /api/v1/query body).

    Raises ``KeyError`` for an unknown model (mapped to 404 by the endpoint).
    """
    model = body.get("model", "")
    messages = body.get("messages", []) or []
    question, history = split_messages(messages)
    route = resolve_model(model, question)
    is_body = {
        "question":  question,
        "top_k":     5,
        "domain":    None,   # module is already selected by upstream port
        "min_score": 0.3,
        "history":   history,
    }
    return route, is_body


# ── IntelligenceSuite response → OpenAI response ──────────────────────────────

def gen_chat_id() -> str:
    return "chatcmpl-" + uuid.uuid4().hex


def is_response_to_openai(
    qr: dict,
    model: str,
    *,
    chat_id: str | None = None,
    created: int | None = None,
) -> dict:
    """Build an OpenAI ``chat.completion`` object from an IS QueryResponse dict."""
    content = qr.get("answer", "") if isinstance(qr, dict) else ""
    return {
        "id":      chat_id or gen_chat_id(),
        "object":  "chat.completion",
        "created": created or int(time.time()),
        "model":   model,
        "choices": [
            {
                "index":         0,
                "message":       {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


# ── SSE: IntelligenceSuite events → OpenAI chunks ─────────────────────────────

def chat_chunk(
    *,
    model: str,
    chat_id: str,
    created: int,
    content: str | None = None,
    role: str | None = None,
    finish_reason: str | None = None,
) -> dict:
    """Build one OpenAI ``chat.completion.chunk`` object."""
    delta: dict = {}
    if role is not None:
        delta["role"] = role
    if content is not None:
        delta["content"] = content
    return {
        "id":      chat_id,
        "object":  "chat.completion.chunk",
        "created": created,
        "model":   model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def is_sse_event_to_openai_chunk(
    event: dict,
    *,
    model: str,
    chat_id: str,
    created: int,
) -> dict | None:
    """Translate ONE IntelligenceSuite SSE event into an OpenAI chunk.

    Only ``token`` events carry assistant text → a content chunk. All other
    event types (``sources``, ``meta``, ``done``, ``error``) return ``None`` and
    are handled by the streaming endpoint (e.g. emitting the final stop chunk).
    """
    if not isinstance(event, dict):
        return None
    if event.get("type") == "token":
        return chat_chunk(
            model=model, chat_id=chat_id, created=created,
            content=event.get("token", ""),
        )
    return None


# ── SSE wire helpers ──────────────────────────────────────────────────────────

def format_sse(data: dict | str) -> str:
    """Serialize a payload as one SSE ``data:`` frame.

    A dict is JSON-encoded; the sentinel string ``"[DONE]"`` is emitted verbatim
    (the OpenAI stream terminator).
    """
    if isinstance(data, str):
        return f"data: {data}\n\n"
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


_SSE_DATA_RE = re.compile(r"^data:\s?(.*)$")


def parse_sse_line(line: str) -> dict | None:
    """Parse one upstream SSE line into an event dict, or ``None`` if not data.

    Tolerates blank lines, comments (``:`` prefix) and the ``[DONE]`` sentinel.
    """
    if not line:
        return None
    m = _SSE_DATA_RE.match(line.strip())
    if not m:
        return None
    payload = m.group(1).strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        obj = json.loads(payload)
        return obj if isinstance(obj, dict) else None
    except (ValueError, TypeError):
        return None
