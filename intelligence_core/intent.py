"""Intent classifier — transparent RAG / Skill / Agent routing for all modules.

Two-stage classifier:
  Stage 1 — heuristic (0 ms, no LLM call): keyword triggers + structural rules.
             If confidence >= threshold → use result directly.
  Stage 2 — minimal LLM call (~300 ms): only for ambiguous cases (confidence < threshold).

Fallback rule: ANY failure (LLM timeout, bad JSON, unexpected error) → RAG, confidence 0.5.
Never crash. Never block the request.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from SkillIntelligence.base import BaseSkill

logger = logging.getLogger(__name__)

# Module-level import so tests can patch intelligence_core.intent.get_llm_provider
from intelligence_core.llm import get_llm_provider  # noqa: E402


# ── Intent levels ─────────────────────────────────────────────────────────────

class IntentLevel(Enum):
    RAG   = "rag"
    SKILL = "skill"
    AGENT = "agent"


@dataclass
class IntentResult:
    level:                IntentLevel
    confidence:           float
    skill_name:           str | None          = None
    skill_parameters:     dict                = field(default_factory=dict)
    parameters_complete:  bool                = False
    reasoning:            str                 = ""


# ── Trigger word lists ────────────────────────────────────────────────────────

_SKILL_TRIGGERS: list[str] = [
    "guidami", "guida", "procedi", "step", "passo", "procedura",
    "come faccio", "come si fa", "come fare", "deploy", "rilascio",
    "onboarding", "inizia", "avvia", "esegui la procedura",
    "walk me through", "step by step", "how do i", "how to",
]

_AGENT_TRIGGERS: list[str] = [
    "analizza", "verifica tutto", "controlla e dimmi", "confronta",
    "cerca in tutto", "dimmi se posso", "fai un'analisi completa",
    "esamina", "indaga", "trova tutte le dipendenze",
    "analyze", "verify everything", "check everything",
    "cross-domain", "full analysis",
]

_CONJUNCTION_PATTERNS = re.compile(
    r"\b(e poi|quindi|dopo|poi|successivamente|infine|and then|then|after that)\b",
    re.IGNORECASE,
)


# ── Stage 1: heuristic classifier ────────────────────────────────────────────

def _heuristic_classify(
    query: str,
    registered_skill_names: list[str],
) -> tuple[IntentLevel, float, str]:
    """
    Returns (level, confidence, reasoning).
    confidence >= threshold means skip Stage 2.
    """
    q_lower = query.lower()

    # Direct skill-name match → very high confidence
    for name in registered_skill_names:
        if name.lower() in q_lower:
            return IntentLevel.SKILL, 0.95, f"nome skill '{name}' trovato nella query"

    # Agent triggers
    for trigger in _AGENT_TRIGGERS:
        if trigger in q_lower:
            return IntentLevel.AGENT, 0.90, f"trigger agent '{trigger}'"

    # Skill triggers
    for trigger in _SKILL_TRIGGERS:
        if trigger in q_lower:
            return IntentLevel.SKILL, 0.88, f"trigger skill '{trigger}'"

    # Long query + conjunctions → likely AGENT
    if len(query) > 120 and _CONJUNCTION_PATTERNS.search(query):
        return IntentLevel.AGENT, 0.75, "query lunga con congiunzioni"

    # Short/simple question → RAG
    if query.strip().endswith("?") and len(query.split()) <= 15:
        return IntentLevel.RAG, 0.80, "domanda breve e diretta"

    # Default: ambiguous → low-confidence RAG, send to Stage 2
    return IntentLevel.RAG, 0.50, "nessun trigger riconosciuto"


# ── Stage 2: LLM classifier ───────────────────────────────────────────────────

def _llm_classify(
    query: str,
    skill_summaries: str,
) -> tuple[IntentLevel, float]:
    """Call the LLM with a minimal prompt. Returns (level, confidence).
    On any failure falls back to (RAG, 0.5).
    """
    prompt = (
        "Classifica questa query in una di tre categorie:\n"
        "- RAG: domanda semplice e diretta su un fatto\n"
        "- SKILL: richiesta di essere guidato in una procedura specifica\n"
        "- AGENT: analisi complessa che richiede ricerca in più domini\n\n"
        f"Query: \"{query}\"\n"
        f"Skill disponibili: {skill_summaries}\n\n"
        'Rispondi SOLO con un JSON: {"level": "rag"|"skill"|"agent", "confidence": 0.0-1.0}'
    )

    try:
        llm = get_llm_provider()
        raw = llm.generate(prompt, "")
        match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON in LLM response: {raw!r}")
        data = json.loads(match.group())
        level_str = str(data.get("level", "rag")).lower()
        confidence = float(data.get("confidence", 0.5))
        level_map = {"rag": IntentLevel.RAG, "skill": IntentLevel.SKILL, "agent": IntentLevel.AGENT}
        return level_map.get(level_str, IntentLevel.RAG), max(0.0, min(1.0, confidence))
    except Exception as exc:
        logger.warning("IntentClassifier: LLM call fallita, fallback a RAG: %s", exc)
        return IntentLevel.RAG, 0.5


# ── Skill Matcher ─────────────────────────────────────────────────────────────

class _RegistryProtocol(Protocol):
    def list_skills(self) -> list[dict]: ...
    def get_skill(self, name: str) -> Any: ...


def match_skill(query: str, registry: _RegistryProtocol) -> tuple[str | None, float]:
    """Find the best-matching skill for a query.

    Strategy (in order):
    1. Exact name match in query → confidence 0.95
    2. Keyword match against description → confidence 0.70–0.85
    3. No match → (None, 0.0)
    """
    q_lower = query.lower()
    skills = registry.list_skills()

    # 1. Exact name match
    for meta in skills:
        name = meta.get("name", "")
        if name and name.lower() in q_lower:
            return name, 0.95

    # 2. Keyword match on description
    best_name: str | None = None
    best_score: float = 0.0
    for meta in skills:
        name = meta.get("name", "")
        description = meta.get("description", "")
        words = [w.lower() for w in re.findall(r'\w+', description) if len(w) > 3]
        if not words:
            continue
        matched = sum(1 for w in words if w in q_lower)
        ratio = matched / len(words)
        score = 0.70 + 0.15 * ratio  # 0.70 → 0.85 range
        if matched >= 2 and score > best_score:
            best_score = score
            best_name = name

    return best_name, best_score


# ── Parameter extractor ───────────────────────────────────────────────────────

def extract_parameters(query: str, skill: Any) -> tuple[dict, bool]:
    """Extract skill parameters from a natural language query via LLM.

    Returns (extracted_params, parameters_complete).
    parameters_complete is True only if ALL required params are present.
    On failure returns ({}, False).
    """
    parameters_spec: dict = getattr(skill, "parameters", {})
    if not parameters_spec:
        return {}, True

    required_params = [
        name for name, spec in parameters_spec.items()
        if spec.get("required", False)
    ]

    prompt = (
        "Estrai i parametri da questa frase.\n"
        f"Parametri richiesti: {json.dumps(parameters_spec, ensure_ascii=False)}\n"
        f"Frase: '{query}'\n"
        "Rispondi SOLO con JSON: {param_name: valore_estratto}\n"
        "Se un parametro non è presente nella frase, omettilo."
    )

    try:
        llm = get_llm_provider()
        raw = llm.generate(prompt, "")
        match = re.search(r'\{[^}]*\}', raw, re.DOTALL)
        if not match:
            extracted: dict = {}
        else:
            extracted = json.loads(match.group())
            if not isinstance(extracted, dict):
                extracted = {}
    except Exception as exc:
        logger.warning("IntentClassifier: estrazione parametri fallita: %s", exc)
        extracted = {}

    complete = all(p in extracted for p in required_params)
    return extracted, complete


# ── Public API ────────────────────────────────────────────────────────────────

def classify_intent(
    query: str,
    registry: _RegistryProtocol | None = None,
) -> IntentResult:
    """Classify query intent and (if SKILL) match a skill + extract parameters.

    Args:
        query:    The user query string.
        registry: SkillRegistry instance (optional — if None, SKILL routing is disabled).

    Returns:
        IntentResult with level, confidence, and optional skill info.
    """
    from intelligence_core.config import settings

    # Routing disabled → always RAG
    if not settings.intent_routing:
        return IntentResult(
            level=IntentLevel.RAG,
            confidence=1.0,
            reasoning="routing disabilitato via INTENT_ROUTING=false",
        )

    registered_names: list[str] = []
    skill_summaries = "nessuna skill disponibile"
    if registry is not None:
        try:
            skills_meta = registry.list_skills()
            registered_names = [m.get("name", "") for m in skills_meta if m.get("name")]
            skill_summaries = "; ".join(
                f"{m['name']}: {m.get('description', '')[:80]}"
                for m in skills_meta
            ) or "nessuna skill disponibile"
        except Exception as exc:
            logger.warning("IntentClassifier: list_skills fallita, registry ignorato: %s", exc)
            registry = None

    # Stage 1: heuristic
    level, confidence, reasoning = _heuristic_classify(query, registered_names)

    # Stage 2: LLM fallback for ambiguous cases
    if confidence < settings.intent_confidence_threshold:
        llm_level, llm_confidence = _llm_classify(query, skill_summaries)
        reasoning = f"stage1={level.value}({confidence:.2f}) → LLM={llm_level.value}({llm_confidence:.2f})"
        level, confidence = llm_level, llm_confidence

    # Agent disabled → fall back to RAG
    if level == IntentLevel.AGENT and not settings.intent_agent_enabled:
        return IntentResult(
            level=IntentLevel.RAG,
            confidence=confidence,
            reasoning=f"AGENT rilevato ma non abilitato ({reasoning}) — fallback RAG",
        )

    # RAG → return early
    if level != IntentLevel.SKILL:
        return IntentResult(level=level, confidence=confidence, reasoning=reasoning)

    # SKILL → match + extract parameters
    if registry is None:
        return IntentResult(
            level=IntentLevel.RAG,
            confidence=0.5,
            reasoning="SKILL rilevato ma nessun registry disponibile — fallback RAG",
        )

    skill_name, match_conf = match_skill(query, registry)
    if skill_name is None:
        return IntentResult(
            level=IntentLevel.RAG,
            confidence=0.5,
            reasoning=f"SKILL rilevato ma nessuna skill trovata per la query — fallback RAG",
        )

    skill_obj = registry.get_skill(skill_name)
    if skill_obj is None:
        return IntentResult(
            level=IntentLevel.RAG,
            confidence=0.5,
            reasoning=f"skill '{skill_name}' non trovata nel registry — fallback RAG",
        )

    params, complete = extract_parameters(query, skill_obj)

    return IntentResult(
        level=IntentLevel.SKILL,
        confidence=min(confidence, match_conf),
        skill_name=skill_name,
        skill_parameters=params,
        parameters_complete=complete,
        reasoning=f"{reasoning} | skill='{skill_name}'(conf={match_conf:.2f}) | params_complete={complete}",
    )
