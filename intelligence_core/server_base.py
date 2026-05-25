"""FastAPI app base — shared by CodeIntelligence, DocIntelligence, MentorIntelligence."""

from __future__ import annotations
import time
import logging

from fastapi import FastAPI
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


def create_app(
    title: str,
    retriever: Retriever,
    policy: EscalationPolicy | None = None,
    llm_provider: LLMProvider | None = None,
) -> FastAPI:
    """
    Build a FastAPI app with:
      GET  /health          — liveness + chunk count
      POST /api/v1/query    — semantic search + LLM answer generation

    Args:
        title:        OpenAPI title shown in /docs.
        retriever:    Configured Retriever (embedder + vector store).
        policy:       Escalation policy; defaults to EscalationPolicy().
        llm_provider: LLM backend; defaults to get_llm_provider() from settings.
                      Pass an explicit provider to override LLM_BACKEND for this app.
    """
    app = FastAPI(title=title, version="0.1.0")
    _policy = policy or EscalationPolicy()
    _llm    = llm_provider or get_llm_provider()

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "chunks_indexed": retriever.store.count(),
            "llm_backend": _llm.backend_name,
            "llm_available": _llm.is_available(),
        }

    @app.post("/api/v1/query", response_model=QueryResponse)
    async def query(req: QueryRequest):
        t0 = time.perf_counter()

        # 1. Retrieve relevant chunks
        results  = retriever.search(req.question, top_k=req.top_k, domain=req.domain)
        filtered = [r for r in results if r.score >= req.min_score]

        sources = [
            {
                "id":     r.chunk.get("id", ""),
                "source": r.chunk.get("source", ""),
                "type":   r.chunk.get("type", ""),
                "score":  round(r.score, 4),
            }
            for r in filtered
        ]
        context    = _build_context(filtered)
        confidence = filtered[0].score if filtered else 0.0

        # 2. Decide whether to escalate to Claude
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
            answer_llm = ClaudeProvider(
                api_key=settings.anthropic_api_key,
                model=settings.claude_model,
            )
            escalated = True
        else:
            answer_llm = _llm

        # 3. Generate answer
        if not filtered:
            answer = (
                "No relevant documents found for your question. "
                "Try re-indexing or rephrasing the query."
            )
        else:
            answer = answer_llm.generate(req.question, context)

        return QueryResponse(
            answer=answer,
            sources=sources,
            confidence=round(confidence, 4),
            escalated=escalated,
            backend=answer_llm.backend_name,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        )

    return app
