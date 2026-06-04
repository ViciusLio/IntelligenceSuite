"""FastAPI app base — shared by CodeIntelligence, DocIntelligence, MentorIntelligence."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from intelligence_core.escalation import EscalationPolicy
from intelligence_core.llm import LLMProvider, get_llm_provider
from intelligence_core.retriever import Retriever

logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    question: str
    top_k:     int   = 5
    domain:    str | None = None
    min_score: float = 0.3
    history:   list[dict] = []   # [{"role": "user"|"assistant", "content": "..."}]


class SkillNextRequest(BaseModel):
    session_id: str
    user_input: str | None = None


class QueryResponse(BaseModel):
    answer:      str
    sources:     list[dict]
    confidence:  float
    escalated:   bool
    backend:     str
    latency_ms:  float
    # Intent routing fields — optional, backward-compatible
    intent:      str         = "rag"   # "rag" | "skill" | "agent" | "agent_stub"
    session_id:  str | None  = None    # present only for Skill responses
    is_last_step: bool | None = None   # present only for Skill responses


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
    skill_registry=None,
    skill_executor=None,
) -> FastAPI:
    """
    Build a FastAPI app with:
      GET  /                    — chat UI (streaming, browser-ready)
      GET  /health              — liveness + chunk count + module name
      POST /api/v1/query        — semantic search + LLM answer, with optional intent routing
      POST /api/v1/stream       — semantic search + LLM answer (SSE streaming)
      POST /api/v1/skill/next   — advance an active Skill session

    Args:
        title:          OpenAPI title shown in /docs.
        retriever:      Configured Retriever (embedder + vector store).
        policy:         Escalation policy; defaults to EscalationPolicy().
        llm_provider:   LLM backend; defaults to get_llm_provider() from settings.
        module:         Module identifier ("code" | "doc" | "mentor") — used by
                        the chat UI to show context-aware suggestion pills.
        skill_registry: Optional SkillRegistry — loaded lazily from SkillIntelligence
                        when routing is enabled and not explicitly provided.
        skill_executor: Optional SkillExecutor — loaded lazily when routing is enabled.
    """
    from intelligence_core.config import settings
    app     = FastAPI(title=title, version="0.2.0")
    _policy = policy or EscalationPolicy(
        threshold=settings.escalation_threshold,
        max_local_tokens=settings.escalation_max_tokens,
    )
    _llm    = llm_provider or get_llm_provider()
    _skill_registry = skill_registry
    _skill_executor = skill_executor

    def _get_skill_registry():
        nonlocal _skill_registry
        if _skill_registry is None:
            try:
                from SkillIntelligence.registry import get_registry
                _skill_registry = get_registry()
            except Exception as exc:
                logger.warning("Intent routing: impossibile caricare SkillRegistry: %s", exc)
        return _skill_registry

    def _get_skill_executor():
        nonlocal _skill_executor
        if _skill_executor is None:
            try:
                from SkillIntelligence.executor import SkillExecutor
                _skill_executor = SkillExecutor(llm=_llm)
            except Exception as exc:
                logger.warning("Intent routing: impossibile creare SkillExecutor: %s", exc)
        return _skill_executor

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Auth (outermost layer — rejects 401 before reaching any handler) ──────
    from intelligence_core.auth import add_auth_middleware, warn_if_key_missing
    add_auth_middleware(app)
    warn_if_key_missing()

    # ── Observability: opt-in GET /metrics (no-op unless IS_METRICS_ENABLED) ──
    from intelligence_core.observability import add_metrics_endpoint
    add_metrics_endpoint(app)

    # ── Ingestion: opt-in ingest routes (no-op unless IS_INGEST_ENABLED) ──────
    from intelligence_core.ingest_api import add_ingest_routes
    add_ingest_routes(app, module=module)

    # ── Export: POST /api/v1/export (Markdown/HTML always, PDF via [export]) ──
    from intelligence_core.export_api import add_export_routes
    add_export_routes(app, module=module)

    # ── Chat UI ───────────────────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def chat_ui():
        from intelligence_ui.templates import CHAT_HTML
        return HTMLResponse(content=CHAT_HTML)

    # ── Health ────────────────────────────────────────────────────────────────
    @app.get("/health")
    def health():
        # NOTE: llm.is_available() deliberately excluded — it makes a synchronous
        # HTTP call to the LLM backend and exceeds the browser AbortSignal timeout,
        # causing the launcher to show the module as offline even when it is running.
        from intelligence_core.config import settings
        # Embedder backend/model the *running process* actually loaded — exposed so
        # a query-vs-index model drift (e.g. server started before ST_MODEL changed)
        # is visible without probing the backend over the network.
        _emb = getattr(retriever, "embedder", None)
        embed_model = getattr(_emb, "model_name", None) or getattr(_emb, "model", None)
        return {
            "status":         "ok",
            "module":         module,
            "chunks_indexed": retriever.store.count(),
            "llm_backend":    _llm.backend_name,
            "embed_backend":  getattr(settings, "embed_backend", None),
            "embed_model":    embed_model,
            "ingest_enabled": bool(getattr(settings, "is_ingest_enabled", False)),
        }

    # ── Non-streaming query ───────────────────────────────────────────────────
    @app.post("/api/v1/query", response_model=QueryResponse)
    async def query(req: QueryRequest):
        from intelligence_core.config import settings
        t0 = time.perf_counter()

        def _observe(resp: QueryResponse) -> QueryResponse:
            """Emit one structured query event (metadata only) + update metrics."""
            from intelligence_core.observability import log_query_event
            log_query_event(
                module=module,
                project=getattr(settings, "is_project", "default"),
                intent=resp.intent,
                question_length=len(req.question),
                top_k=req.top_k,
                confidence=resp.confidence,
                escalated=resp.escalated,
                backend=resp.backend,
                latency_ms=resp.latency_ms,
            )
            return resp

        # ── Intent routing (transparent to the caller) ────────────────────────
        if settings.intent_routing:
            from intelligence_core.intent import IntentLevel, classify_intent
            try:
                intent = classify_intent(req.question, registry=_get_skill_registry())
            except Exception as exc:
                logger.warning("Intent classify error, fallback RAG: %s", exc)
                intent = None

            if intent is not None and intent.level == IntentLevel.AGENT and settings.intent_agent_enabled:
                # ── Agent path ─────────────────────────────────────────────────
                try:
                    from AgentIntelligence.agent import run_agent as _run_agent
                    result = await asyncio.to_thread(
                        _run_agent,
                        req.question,
                        _llm,
                        settings.agent_max_iterations,
                        settings.thinking_mode,
                    )
                    return _observe(QueryResponse(
                        answer=result["answer"],
                        sources=[],
                        confidence=round(intent.confidence, 4),
                        escalated=False,
                        backend=_llm.backend_name,
                        latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                        intent="agent",
                    ))
                except Exception as exc:
                    logger.warning("Agent run fallita, fallback RAG: %s", exc)

            if intent is not None and intent.level == IntentLevel.SKILL:
                if not intent.parameters_complete:
                    # Ask for missing parameters — natural language, not an error
                    executor_obj = _get_skill_executor()
                    registry_obj = _get_skill_registry()
                    skill_obj = registry_obj.get_skill(intent.skill_name) if registry_obj else None
                    if skill_obj is not None:
                        missing = [
                            p for p, spec in skill_obj.parameters.items()
                            if spec.get("required") and p not in intent.skill_parameters
                        ]
                        q_text = (
                            f"Per guidarti nel processo '{intent.skill_name}' ho bisogno di sapere: "
                            + ", ".join(f"**{p}**" for p in missing) + "."
                        )
                        if "environment" in missing:
                            q_text += " (es: staging o production)"
                        return _observe(QueryResponse(
                            answer=q_text,
                            sources=[],
                            confidence=round(intent.confidence, 4),
                            escalated=False,
                            backend=_llm.backend_name,
                            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                            intent="skill",
                        ))

                # Start skill session and return first step
                executor_obj = _get_skill_executor()
                registry_obj = _get_skill_registry()
                if executor_obj is not None and registry_obj is not None:
                    skill_obj = registry_obj.get_skill(intent.skill_name)
                    if skill_obj is not None:
                        try:
                            session_id, first_step = await asyncio.to_thread(
                                executor_obj.start_session, skill_obj, intent.skill_parameters
                            )
                            answer = f"**{first_step.title}**\n\n{first_step.guidance}"
                            if first_step.sources:
                                answer += "\n\n_Fonti: " + ", ".join(
                                    s["source"] for s in first_step.sources if s.get("source")
                                ) + "_"
                            return _observe(QueryResponse(
                                answer=answer,
                                sources=first_step.sources,
                                confidence=round(intent.confidence, 4),
                                escalated=False,
                                backend=_llm.backend_name,
                                latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                                intent="skill",
                                session_id=session_id,
                                is_last_step=first_step.is_last_step,
                            ))
                        except Exception as exc:
                            logger.warning("Skill session start fallita, fallback RAG: %s", exc)

        # ── Standard RAG path ─────────────────────────────────────────────────
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

        return _observe(QueryResponse(
            answer=answer,
            sources=sources,
            confidence=round(confidence, 4),
            escalated=escalated,
            backend=answer_llm.backend_name,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
            intent="rag",
        ))

    # ── Skill next-step endpoint (available on all modules) ───────────────────
    @app.post("/api/v1/skill/next")
    async def skill_next(req: SkillNextRequest):
        from fastapi import HTTPException as _HTTPException
        executor_obj = _get_skill_executor()
        if executor_obj is None:
            raise _HTTPException(status_code=503, detail="SkillExecutor non disponibile")
        try:
            result = await asyncio.to_thread(executor_obj.next_step, req.session_id, req.user_input)
        except KeyError as exc:
            raise _HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise _HTTPException(status_code=500, detail=str(exc))

        if result is None:
            return QueryResponse(
                answer="Procedura completata.",
                sources=[],
                confidence=1.0,
                escalated=False,
                backend=_llm.backend_name,
                latency_ms=0.0,
                intent="skill",
                is_last_step=True,
            )

        answer = f"**{result.title}**\n\n{result.guidance}"
        if result.sources:
            answer += "\n\n_Fonti: " + ", ".join(
                s["source"] for s in result.sources if s.get("source")
            ) + "_"
        return QueryResponse(
            answer=answer,
            sources=result.sources,
            confidence=1.0,
            escalated=False,
            backend=_llm.backend_name,
            latency_ms=0.0,
            intent="skill",
            session_id=result.session_id,
            is_last_step=result.is_last_step,
        )

    # ── Streaming query (SSE) ─────────────────────────────────────────────────
    @app.post("/api/v1/stream")
    async def stream_query(req: QueryRequest):
        from intelligence_core.config import settings
        t0 = time.perf_counter()

        def _log_stream(intent: str, confidence: float, escalated: bool, backend: str) -> None:
            """Emit one structured query event (metadata only) + update metrics.

            Called once the SSE response has been fully generated so streaming
            queries are counted in /metrics alongside non-streaming ones.
            """
            from intelligence_core.observability import log_query_event
            log_query_event(
                module=module,
                project=getattr(settings, "is_project", "default"),
                intent=intent,
                question_length=len(req.question),
                top_k=req.top_k,
                confidence=confidence,
                escalated=escalated,
                backend=backend,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        # ── Intent routing ────────────────────────────────────────────────────
        if settings.intent_routing:
            from intelligence_core.intent import IntentLevel, classify_intent
            try:
                intent = classify_intent(req.question, registry=_get_skill_registry())
            except Exception as exc:
                logger.warning("stream_query: intent classify error, fallback RAG: %s", exc)
                intent = None

            if intent is not None and intent.level == IntentLevel.AGENT and settings.intent_agent_enabled:
                # ── Agent path (SSE — stream word by word) ─────────────────────
                try:
                    from AgentIntelligence.agent import run_agent as _run_agent
                    result = await asyncio.to_thread(
                        _run_agent,
                        req.question,
                        _llm,
                        settings.agent_max_iterations,
                        settings.thinking_mode,
                    )
                    agent_text = result["answer"]
                    agent_tools = result.get("tools_used", [])

                    async def agent_stream():
                        yield f"data: {json.dumps({'type': 'sources', 'sources': []})}\n\n"
                        for word in agent_text.split(" "):
                            yield f"data: {json.dumps({'type': 'token', 'token': word + ' '})}\n\n"
                        yield f"data: {json.dumps({'type': 'meta', 'confidence': round(intent.confidence, 4), 'backend': _llm.backend_name, 'escalated': False, 'intent': 'agent', 'tools_used': agent_tools})}\n\n"
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        _log_stream("agent", intent.confidence, False, _llm.backend_name)

                    return StreamingResponse(
                        agent_stream(),
                        media_type="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                    )
                except Exception as exc:
                    logger.warning("stream_query: agent run fallita, fallback RAG: %s", exc)

            if intent is not None and intent.level == IntentLevel.SKILL:
                answer_text: str | None = None
                skill_sources: list[dict] = []
                session_id: str | None = None

                if not intent.parameters_complete:
                    registry_obj = _get_skill_registry()
                    skill_obj = registry_obj.get_skill(intent.skill_name) if registry_obj else None
                    if skill_obj is not None:
                        missing = [
                            p for p, spec in skill_obj.parameters.items()
                            if spec.get("required") and p not in intent.skill_parameters
                        ]
                        answer_text = (
                            f"Per guidarti nel processo '{intent.skill_name}' "
                            "ho bisogno di sapere: "
                            + ", ".join(f"**{p}**" for p in missing) + "."
                        )
                        if "environment" in missing:
                            answer_text += " (es: staging o production)"
                else:
                    executor_obj = _get_skill_executor()
                    registry_obj = _get_skill_registry()
                    if executor_obj is not None and registry_obj is not None:
                        skill_obj = registry_obj.get_skill(intent.skill_name)
                        if skill_obj is not None:
                            try:
                                session_id, first_step = await asyncio.to_thread(
                                    executor_obj.start_session,
                                    skill_obj,
                                    intent.skill_parameters,
                                )
                                answer_text = f"**{first_step.title}**\n\n{first_step.guidance}"
                                skill_sources = first_step.sources
                            except Exception as exc:
                                logger.warning(
                                    "stream_query: skill session start fallita, fallback RAG: %s", exc
                                )

                if answer_text is not None:
                    async def skill_stream():
                        yield f"data: {json.dumps({'type': 'sources', 'sources': skill_sources})}\n\n"
                        for word in answer_text.split(" "):
                            yield f"data: {json.dumps({'type': 'token', 'token': word + ' '})}\n\n"
                        meta: dict = {
                            "type": "meta",
                            "confidence": round(intent.confidence, 4),
                            "backend": _llm.backend_name,
                            "escalated": False,
                            "intent": "skill",
                        }
                        if session_id:
                            meta["session_id"] = session_id
                        yield f"data: {json.dumps(meta)}\n\n"
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        _log_stream("skill", intent.confidence, False, _llm.backend_name)

                    return StreamingResponse(
                        skill_stream(),
                        media_type="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                    )

        # ── Standard RAG streaming ────────────────────────────────────────────
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
                _log_stream("rag", confidence, escalated, answer_llm.backend_name)
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
            _log_stream("rag", confidence, escalated, answer_llm.backend_name)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app
