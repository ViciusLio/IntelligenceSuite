"""FastAPI app base — shared by CodeIntelligence, DocIntelligence, MentorIntelligence."""

from __future__ import annotations
import asyncio
import json
import threading
import time
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from intelligence_core.retriever import Retriever
from intelligence_core.escalation import EscalationPolicy
from intelligence_core.llm import LLMProvider, get_llm_provider

logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    question: str
    top_k:     int   = 5
    domain:    str | None = None
    min_score: float = 0.3
    history:   list[dict] = []   # [{"role": "user"|"assistant", "content": "..."}]


class QueryResponse(BaseModel):
    answer:      str
    sources:     list[dict]
    confidence:  float
    escalated:   bool
    backend:     str
    latency_ms:  float


def _build_context(results: list) -> str:
    """Concatenate top chunk texts into a single context string."""
    parts = []
    for r in results[:5]:
        src = r.chunk.get("source", "unknown")
        parts.append(f"[{src}]\n{r.chunk['text']}")
    return "\n\n---\n\n".join(parts)


def _build_context_with_history(context: str, history: list[dict]) -> str:
    """Prepend the last conversation turns to the retrieval context."""
    if not history:
        return context
    turns = "\n".join(
        f"{m['role'].upper()}: {m['content'][:400]}"
        for m in history[-6:]
    )
    if not context:
        return f"[Conversazione precedente]\n{turns}"
    return f"[Conversazione precedente]\n{turns}\n\n[Documenti recuperati]\n{context}"


async def _rewrite_query(question: str, history: list[dict], llm) -> str:
    """If the question looks like a follow-up, rewrite it as a standalone search query."""
    if not history:
        return question

    q_lower = question.lower()
    is_short = len(question.split()) <= 7
    followup_signals = [
        "it", "that", "this", "those", "them", "more", "detail", "explain",
        "elaborate", "also", "why", "how", "what about",
        "quello", "questa", "questo", "queste", "questi",
        "di più", "approfondisci", "spiegami", "perché", "come mai",
        "inoltre", "ancora", "altro", "altri", "altra",
    ]
    has_signal = any(s in q_lower for s in followup_signals)

    if not is_short and not has_signal:
        return question  # query già autoesplicativa

    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content'][:300]}"
        for m in history[-4:]
    )
    prompt = (
        f"Conversazione:\n{history_text}\n\n"
        f"Riscrivi questa domanda come query di ricerca autonoma e completa "
        f"(sostituisci pronomi e riferimenti con termini espliciti, "
        f"includi il contesto necessario per capirla senza la conversazione):\n"
        f"\"{question}\"\n\n"
        f"Rispondi SOLO con la query riscritta, nessuna spiegazione."
    )
    try:
        rewritten = await asyncio.to_thread(llm.generate, prompt, "")
        rewritten = rewritten.strip().strip('"').strip("'").split("\n")[0]
        logger.info("Query rewrite: %r → %r", question, rewritten)
        return rewritten if rewritten else question
    except Exception as exc:
        logger.warning("Query rewrite failed: %s — using original", exc)
        return question


def _build_sources(filtered: list) -> list[dict]:
    return [
        {
            "id":     r.chunk.get("id", ""),
            "source": r.chunk.get("source", ""),
            "type":   r.chunk.get("type", ""),
            "score":  round(r.score, 4),
        }
        for r in filtered
    ]


async def _async_stream(llm, question: str, context: str):
    """Bridge a sync LLM stream() generator into an async generator."""
    loop  = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _producer():
        try:
            stream_fn = getattr(llm, "stream", None)
            if stream_fn:
                for token in stream_fn(question, context):
                    loop.call_soon_threadsafe(queue.put_nowait, token)
            else:
                # Fallback: call generate() and yield whole response
                text = llm.generate(question, context)
                loop.call_soon_threadsafe(queue.put_nowait, text)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, f"\n\n[Error: {exc}]")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=_producer, daemon=True).start()

    while True:
        token = await queue.get()
        if token is None:
            break
        yield token


def create_app(
    title: str,
    retriever: Retriever,
    policy: EscalationPolicy | None = None,
    llm_provider: LLMProvider | None = None,
    module: str = "code",
) -> FastAPI:
    """
    Build a FastAPI app with:
      GET  /               — chat UI (streaming, browser-ready)
      GET  /health         — liveness + chunk count + module name
      POST /api/v1/query   — semantic search + LLM answer (non-streaming)
      POST /api/v1/stream  — semantic search + LLM answer (SSE streaming)

    Args:
        title:        OpenAPI title shown in /docs.
        retriever:    Configured Retriever (embedder + vector store).
        policy:       Escalation policy; defaults to EscalationPolicy().
        llm_provider: LLM backend; defaults to get_llm_provider() from settings.
        module:       Module identifier ("code" | "doc" | "mentor") — used by
                      the chat UI to show context-aware suggestion pills.
    """
    app     = FastAPI(title=title, version="0.2.0")
    _policy = policy or EscalationPolicy()
    _llm    = llm_provider or get_llm_provider()

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Chat UI ───────────────────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def chat_ui():
        from intelligence_ui.templates import CHAT_HTML
        return HTMLResponse(content=CHAT_HTML)

    # ── Health ────────────────────────────────────────────────────────────────
    @app.get("/health")
    def health():
        return {
            "status":         "ok",
            "module":         module,
            "chunks_indexed": retriever.store.count(),
            "llm_backend":    _llm.backend_name,
            "llm_available":  _llm.is_available(),
        }

    # ── Non-streaming query ───────────────────────────────────────────────────
    @app.post("/api/v1/query", response_model=QueryResponse)
    async def query(req: QueryRequest):
        t0 = time.perf_counter()

        # Rewrite follow-up questions using conversation history
        effective_q = await _rewrite_query(req.question, req.history, _llm)

        results  = retriever.search(effective_q, top_k=req.top_k, domain=req.domain)
        filtered = [r for r in results if r.score >= req.min_score]
        sources  = _build_sources(filtered)
        context  = _build_context_with_history(_build_context(filtered), req.history)
        confidence = filtered[0].score if filtered else 0.0

        elapsed_ms = (time.perf_counter() - t0) * 1000
        should_escalate = _policy.should_escalate(
            confidence=confidence,
            query_tokens=len(req.question.split()),
            elapsed_ms=elapsed_ms,
        )

        from intelligence_core.config import settings
        escalated = False
        if should_escalate and settings.anthropic_api_key and _llm.backend_name != "claude":
            from intelligence_core.llm.claude import ClaudeProvider
            answer_llm = ClaudeProvider(api_key=settings.anthropic_api_key, model=settings.claude_model)
            escalated  = True
        else:
            answer_llm = _llm

        answer = (
            "No relevant documents found. Try re-indexing or rephrasing the query."
            if not filtered
            else answer_llm.generate(req.question, context)
        )

        return QueryResponse(
            answer=answer,
            sources=sources,
            confidence=round(confidence, 4),
            escalated=escalated,
            backend=answer_llm.backend_name,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        )

    # ── Streaming query (SSE) ─────────────────────────────────────────────────
    @app.post("/api/v1/stream")
    async def stream_query(req: QueryRequest):
        # Rewrite follow-up questions using conversation history
        effective_q = await _rewrite_query(req.question, req.history, _llm)

        results  = retriever.search(effective_q, top_k=req.top_k, domain=req.domain)
        filtered = [r for r in results if r.score >= req.min_score]
        sources  = _build_sources(filtered)
        context  = _build_context_with_history(_build_context(filtered), req.history)
        confidence = filtered[0].score if filtered else 0.0

        from intelligence_core.config import settings
        should_escalate = _policy.should_escalate(
            confidence=confidence,
            query_tokens=len(req.question.split()),
            elapsed_ms=0,
        )
        escalated = False
        if should_escalate and settings.anthropic_api_key and _llm.backend_name != "claude":
            from intelligence_core.llm.claude import ClaudeProvider
            answer_llm = ClaudeProvider(api_key=settings.anthropic_api_key, model=settings.claude_model)
            escalated  = True
        else:
            answer_llm = _llm

        async def generate():
            # 1. Send sources immediately
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

            # 2. No context → short-circuit
            if not filtered:
                msg = "No relevant documents found. Try re-indexing or rephrasing the query."
                yield f"data: {json.dumps({'type': 'token', 'token': msg})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            # 3. Stream tokens
            try:
                async for token in _async_stream(answer_llm, req.question, context):
                    yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"

            # 4. Done + meta
            yield f"data: {json.dumps({'type': 'meta', 'confidence': round(confidence, 4), 'backend': answer_llm.backend_name, 'escalated': escalated})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app
