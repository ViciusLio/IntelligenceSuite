"""Server REST per ProposalIntelligence.

Endpoint:
  GET  /health                      — stato + numero coppie indicizzate + backend LLM
  POST /api/v1/proposal/answer      — risposte in stile a una lista di domande
"""

from __future__ import annotations

import asyncio
import json
import threading

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from intelligence_core.config import settings
from intelligence_core.store import ChromaStore
from ProposalIntelligence.answer import answer_questions
from ProposalIntelligence.prompts import (
    build_fewshot_context,
    system_prompt_for,
    temperature_for,
)
from ProposalIntelligence.web import PROPOSAL_HTML


class AnswerRequest(BaseModel):
    questions: list[str]
    mode:  str | None = None     # "anchored" | "commercial"
    top_k: int | None = None


class QueryRequest(BaseModel):
    """Single-question contract, mirroring the other modules' /api/v1/query.

    Extra OpenAI-gateway fields (history/min_score/domain) are ignored — only
    the question, an optional top_k and an optional style mode are used.
    """
    question: str
    top_k: int | None = None
    mode:  str | None = None     # "anchored" | "commercial"


async def _stream_styled_tokens(llm, question: str, context: str,
                                system_prompt: str, temperature: float):
    """Bridge a sync styled LLM ``stream()`` into an async token generator.

    Mirrors ``server_base._async_stream`` but forwards the proposal style
    (system prompt + temperature). Falls back to ``generate()`` for providers
    without a ``stream()`` method (e.g. Claude).
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _producer():
        try:
            stream_fn = getattr(llm, "stream", None)
            if stream_fn:
                for token in stream_fn(question, context,
                                       system_prompt=system_prompt,
                                       temperature=temperature):
                    loop.call_soon_threadsafe(queue.put_nowait, token)
            else:
                text = llm.generate(question, context,
                                    system_prompt=system_prompt,
                                    temperature=temperature)
                loop.call_soon_threadsafe(queue.put_nowait, text)
        except Exception as exc:  # noqa: BLE001 — surfaced inline to the client
            loop.call_soon_threadsafe(queue.put_nowait, f"\n\n[Error: {exc}]")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=_producer, daemon=True).start()

    while True:
        token = await queue.get()
        if token is None:
            break
        yield token


class AnswerItem(BaseModel):
    question: str
    answer:   str
    sources:  list[dict]


class AnswerResponse(BaseModel):
    mode:    str
    backend: str
    answers: list[AnswerItem]


def build_app() -> FastAPI:
    app = FastAPI(title="ProposalIntelligence Server", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from intelligence_core.auth import add_auth_middleware, warn_if_key_missing
    add_auth_middleware(app)
    warn_if_key_missing()

    from intelligence_core.observability import add_metrics_endpoint
    add_metrics_endpoint(app)

    from intelligence_core.ingest_api import add_ingest_routes
    add_ingest_routes(app, module="proposal")

    from intelligence_core.export_api import add_export_routes
    add_export_routes(app, module="proposal")

    from intelligence_core import paths
    store = ChromaStore(collection_name=paths.collection_name("qa"),
                        persist_dir=str(paths.chroma_dir()))

    # Shared retriever for the single-question endpoints (query/stream). Built
    # once and reused; same store/embedder the batch answerer uses.
    from intelligence_core.embedder import get_module_embedder
    from intelligence_core.retriever import Retriever
    retriever = Retriever(embedder=get_module_embedder("pi"), store=store)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index():
        return HTMLResponse(content=PROPOSAL_HTML)

    @app.get("/health")
    def health():
        from intelligence_core.llm import get_module_llm_provider
        # Configured embedder (pi override → global fallback) without instantiating
        # it; lets clients spot a query-vs-index model drift.
        embed_backend = getattr(settings, "pi_embed_backend", "") or settings.embed_backend
        embed_model = getattr(settings, "pi_embed_model", "") or (
            settings.st_model if embed_backend == "st"
            else getattr(settings, "ollama_embed_model", None)
        )
        return {
            "status":         "ok",
            "module":         "proposal",
            "chunks_indexed": store.count(),
            "llm_backend":    get_module_llm_provider("pi").backend_name,
            "embed_backend":  embed_backend,
            "embed_model":    embed_model,
            "default_mode":   settings.proposal_mode,
            "ingest_enabled": bool(getattr(settings, "is_ingest_enabled", False)),
        }

    @app.post("/api/v1/proposal/answer", response_model=AnswerResponse)
    def answer(req: AnswerRequest):
        from intelligence_core.llm import get_module_llm_provider
        mode = req.mode or settings.proposal_mode
        llm = get_module_llm_provider("pi")
        answered = answer_questions(
            req.questions, mode=mode, top_k=req.top_k, llm=llm
        )
        return AnswerResponse(
            mode=mode,
            backend=llm.backend_name,
            answers=[
                AnswerItem(question=a.question, answer=a.answer, sources=a.sources)
                for a in answered
            ],
        )

    # ── Single-question RAG (parity with the other modules) ───────────────────
    # The OpenAI gateway speaks one-question-at-a-time; these endpoints let
    # ProposalIntelligence be driven like code/doc/mentor (chat + streaming),
    # while /api/v1/proposal/answer stays for the questionnaire batch workflow.

    @app.post("/api/v1/query")
    def query(req: QueryRequest):
        from intelligence_core.llm import get_module_llm_provider
        mode = req.mode or settings.proposal_mode
        llm = get_module_llm_provider("pi")
        answered = answer_questions(
            [req.question], mode=mode, top_k=req.top_k,
            retriever=retriever, llm=llm,
        )[0]
        return {
            "answer":  answered.answer,
            "sources": answered.sources,
            "backend": llm.backend_name,
            "mode":    mode,
        }

    @app.post("/api/v1/stream")
    async def stream(req: QueryRequest):
        from intelligence_core.llm import get_module_llm_provider
        mode = req.mode or settings.proposal_mode
        top_k = req.top_k or settings.proposal_top_k
        llm = get_module_llm_provider("pi")

        hits = retriever.search(req.question, top_k=top_k, domain=None)
        context = build_fewshot_context(hits)
        sources = [
            {
                "source": (getattr(h, "chunk", h) or {}).get("source", ""),
                "score": round(getattr(h, "score", 0.0), 4),
            }
            for h in hits
        ]
        sys_prompt = system_prompt_for(mode)
        temperature = temperature_for(mode)

        async def event_stream():
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources}, ensure_ascii=False)}\n\n"
            async for token in _stream_styled_tokens(
                llm, req.question, context, sys_prompt, temperature
            ):
                yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'meta', 'backend': llm.backend_name, 'mode': mode}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = build_app()


def main():
    uvicorn.run(
        "ProposalIntelligence.proposal_server:app",
        host=settings.api_host,
        port=settings.pi_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
