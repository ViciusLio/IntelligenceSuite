"""FastAPI app base riusabile da CodeIntelligence e DocIntelligence."""

from __future__ import annotations
import time
import logging

from fastapi import FastAPI
from pydantic import BaseModel

from intelligence_core.retriever import Retriever
from intelligence_core.escalation import EscalationPolicy

logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    domain: str = None
    min_score: float = 0.0


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]
    confidence: float
    escalated: bool
    latency_ms: float


def _call_local_llm(context: str, question: str) -> str:
    """Chiama Ollama per generare la risposta. Fallback a risposta contestuale."""
    import httpx
    from intelligence_core.config import settings
    try:
        prompt = (
            f"Contesto:\n{context}\n\n"
            f"Domanda: {question}\n\n"
            "Rispondi in modo preciso e conciso basandoti solo sul contesto fornito."
        )
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/generate",
            json={"model": settings.ollama_model, "prompt": prompt, "stream": False},
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        logger.warning("LLM locale non disponibile: %s", e)
        return f"[LLM non disponibile] Fonte più rilevante:\n{context[:500]}"


def _call_claude(context: str, question: str) -> str:
    """Chiama Claude API come escalation. Richiede ANTHROPIC_API_KEY."""
    import httpx
    from intelligence_core.config import settings
    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1024,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"Contesto:\n{context}\n\nDomanda: {question}\n\n"
                        "Rispondi in modo preciso basandoti sul contesto."
                    ),
                }],
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
    except Exception as e:
        logger.error("Claude API fallita: %s", e)
        return f"[Escalation fallita] {str(e)}"


def create_app(
    title: str,
    retriever: Retriever,
    policy: EscalationPolicy = None,
) -> FastAPI:
    """Crea l'app FastAPI con endpoint /health e /api/v1/query."""
    app = FastAPI(title=title, version="0.1.0")
    policy = policy or EscalationPolicy()

    @app.get("/health")
    def health():
        return {"status": "ok", "chunks_indexed": retriever.store.count()}

    @app.post("/api/v1/query", response_model=QueryResponse)
    async def query(req: QueryRequest):
        t0 = time.perf_counter()

        results = retriever.search(req.question, top_k=req.top_k, domain=req.domain)
        filtered = [r for r in results if r.score >= req.min_score]

        sources = [
            {"id": r.chunk["id"], "score": r.score, "source": r.chunk.get("source", ""),
             "type": r.chunk.get("type", "")}
            for r in filtered
        ]
        context = "\n\n---\n\n".join(r.chunk["text"] for r in filtered[:3])
        confidence = filtered[0].score if filtered else 0.0

        elapsed_ms = (time.perf_counter() - t0) * 1000
        escalated = policy.should_escalate(
            confidence=confidence,
            query_tokens=len(req.question.split()),
            elapsed_ms=elapsed_ms,
        )

        from intelligence_core.config import settings
        if escalated and settings.anthropic_api_key:
            answer = _call_claude(context, req.question)
        else:
            answer = _call_local_llm(context, req.question)
            escalated = False

        return QueryResponse(
            answer=answer,
            sources=sources,
            confidence=confidence,
            escalated=escalated,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

    return app
