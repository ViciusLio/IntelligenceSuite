"""Retriever: embedding + store + keyword reranking."""

from __future__ import annotations
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    chunk: dict
    score: float
    rank: int


class Retriever:
    """Orchestr embedder + store con keyword reranking."""

    def __init__(self, embedder, store):
        self.embedder = embedder
        self.store = store

    def search(
        self,
        query: str,
        top_k: int = 5,
        domain: str = None,
    ) -> list[RetrievalResult]:
        """Retrieval semantico + reranking per keyword boost."""
        embedding = self.embedder.embed_one(query)
        filters = {"domain": domain} if domain else None
        raw = self.store.search(embedding, top_k=top_k * 2, filters=filters)

        # Keyword boost: +0.1 per ogni termine trovato, cap a +0.3
        query_terms = [t.lower() for t in query.split() if len(t) > 2]
        for chunk in raw:
            text_lower = chunk["text"].lower()
            boost = min(sum(0.1 for t in query_terms if t in text_lower), 0.3)
            chunk["score"] = chunk.get("score", 0.0) + boost

        raw.sort(key=lambda c: c["score"], reverse=True)
        return [
            RetrievalResult(chunk=c, score=c["score"], rank=i + 1)
            for i, c in enumerate(raw[:top_k])
        ]

    @classmethod
    def load_default(cls) -> "Retriever":
        """Factory con embedder e store di default."""
        from intelligence_core.embedder import get_embedder
        from intelligence_core.store import get_store
        return cls(embedder=get_embedder(), store=get_store())
