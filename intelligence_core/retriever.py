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
        """Retrieval semantico → rerank (cross-encoder o keyword) → top_k."""
        from intelligence_core.config import settings
        from intelligence_core.reranker import get_reranker

        embedding = self.embedder.embed_one(query)
        filters = {"domain": domain} if domain else None

        reranker = get_reranker()
        # Col cross-encoder allarghiamo il pool di candidati: più materiale da
        # riordinare = più chance che i chunk rilevanti finiscano nel top_k.
        fetch_k = max(top_k * 2, settings.rerank_candidates) if reranker else top_k * 2
        raw = self.store.search(embedding, top_k=fetch_k, filters=filters)

        if reranker:
            top_chunks = reranker.rerank(query, raw, top_k=top_k)
        else:
            top_chunks = self._keyword_rerank(query, raw, top_k=top_k)

        results = [
            RetrievalResult(chunk=c, score=c["score"], rank=i + 1)
            for i, c in enumerate(top_chunks)
        ]

        # GraphRAG — espansione opzionale via grafo, non breaking.
        if domain == "code":
            results = self._expand_with_graph(results, domain)

        return results

    @staticmethod
    def _keyword_rerank(query: str, raw: list[dict], top_k: int) -> list[dict]:
        """Fallback legacy: boost +0.1 per termine trovato, cap a +0.3."""
        query_terms = [t.lower() for t in query.split() if len(t) > 2]
        for chunk in raw:
            text_lower = chunk["text"].lower()
            boost = min(sum(0.1 for t in query_terms if t in text_lower), 0.3)
            chunk["score"] = chunk.get("score", 0.0) + boost
        raw.sort(key=lambda c: c["score"], reverse=True)
        return raw[:top_k]

    def _expand_with_graph(self, results, domain):
        try:
            from intelligence_core.graph.store import graph_exists

            if not graph_exists(domain):
                return results
            from intelligence_core.graph.retriever import GraphRetriever

            graph_retriever = GraphRetriever(domain)
            semantic_ids = [r.chunk["id"] for r in results]
            graph_ids = graph_retriever.expand_context(semantic_ids, depth=1)
            if not graph_ids:
                return results
            if not hasattr(self.store, "get_by_ids"):
                return results
            existing = set(semantic_ids)
            extra_chunks = [
                c for c in self.store.get_by_ids(graph_ids)
                if c["id"] not in existing
            ]
            base_rank = len(results)
            additional = [
                RetrievalResult(chunk=c, score=c.get("score", 0.0), rank=base_rank + i + 1)
                for i, c in enumerate(extra_chunks)
            ]
            return results + additional
        except Exception as e:
            logger.warning("GraphRAG expansion failed: %s", e)
            return results

    @classmethod
    def load_default(cls, collection_name: str = "code_intelligence") -> "Retriever":
        """Factory con embedder e store di default.

        Args:
            collection_name: ChromaDB collection to connect to.
                Defaults to ``"code_intelligence"``.
                Use ``"doc_intelligence"`` for DocIntelligence,
                ``"mentor_intelligence"`` for MentorIntelligence.
        """
        from intelligence_core.embedder import get_embedder
        from intelligence_core.store import ChromaStore
        return cls(embedder=get_embedder(), store=ChromaStore(collection_name=collection_name))
