"""Vector store: ChromaDB (default) e PgVector (skeleton roadmap v0.2)."""

from __future__ import annotations
import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class VectorStore(Protocol):
    def add(self, chunks: list[dict]) -> None: ...
    def search(self, embedding: list[float], top_k: int, filters: dict = None) -> list[dict]: ...
    def delete(self, chunk_ids: list[str]) -> None: ...
    def count(self) -> int: ...


class ChromaStore:
    """Vector store basato su ChromaDB embedded."""

    def __init__(self, collection_name: str = "intelligence_suite", persist_dir: str = None):
        import chromadb
        from intelligence_core.config import settings
        persist_dir = persist_dir or settings.chroma_persist_dir
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._col = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, chunks: list[dict]) -> None:
        valid = [c for c in chunks if c.get("embedding") and len(c["embedding"]) > 0]
        if not valid:
            logger.warning("add(): nessun chunk con embedding valido")
            return
        # Deduplicate by ID — silently keep first occurrence
        seen: set[str] = set()
        deduped = []
        for c in valid:
            if c["id"] not in seen:
                seen.add(c["id"])
                deduped.append(c)
        if len(deduped) < len(valid):
            logger.warning("add(): removed %d duplicate IDs", len(valid) - len(deduped))
        valid = deduped
        self._col.upsert(
            ids=[c["id"] for c in valid],
            embeddings=[c["embedding"] for c in valid],
            documents=[c["text"] for c in valid],
            metadatas=[
                {k: v for k, v in {
                    **c.get("metadata", {}),
                    "domain":   c.get("domain", ""),
                    "type":     c.get("type", ""),
                    "source":   c.get("source", ""),
                    "language": c.get("language", ""),
                    "checksum": c.get("checksum", ""),
                }.items() if isinstance(v, (str, int, float, bool))}
                for c in valid
            ],
        )

    def search(self, embedding: list[float], top_k: int = 5, filters: dict = None) -> list[dict]:
        where = filters or None
        res = self._col.query(
            query_embeddings=[embedding],
            n_results=min(top_k, max(self._col.count(), 1)),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        chunks = []
        for i, doc_id in enumerate(res["ids"][0]):
            meta = res["metadatas"][0][i]
            distance = res["distances"][0][i]
            chunks.append({
                "id":       doc_id,
                "text":     res["documents"][0][i],
                "domain":   meta.get("domain", ""),
                "type":     meta.get("type", ""),
                "source":   meta.get("source", ""),
                "language": meta.get("language", ""),
                "metadata": meta,
                "score":    1.0 - distance,
            })
        return chunks

    def delete(self, chunk_ids: list[str]) -> None:
        self._col.delete(ids=chunk_ids)

    def count(self) -> int:
        return self._col.count()


class PgVectorStore:
    """Skeleton pgvector — implementazione completa in roadmap v0.2."""

    def __init__(self, dsn: str = None, collection_name: str = "intelligence_suite"):
        raise NotImplementedError(
            "PgVectorStore è pianificato per v0.2. "
            "Usa ChromaStore per ora. "
            "Contributi benvenuti: https://github.com/ViciusLio/IntelligenceSuite"
        )

    def add(self, chunks: list[dict]) -> None: ...
    def search(self, embedding: list[float], top_k: int, filters: dict = None) -> list[dict]: ...
    def delete(self, chunk_ids: list[str]) -> None: ...
    def count(self) -> int: ...


def get_store(backend: str = None, collection_name: str = "intelligence_suite") -> VectorStore:
    """Factory: crea il vector store appropriato in base a settings.vector_store."""
    from intelligence_core.config import settings
    backend = backend or settings.vector_store
    if backend == "pgvector":
        return PgVectorStore(dsn=settings.pgvector_dsn, collection_name=collection_name)
    return ChromaStore(collection_name=collection_name)
