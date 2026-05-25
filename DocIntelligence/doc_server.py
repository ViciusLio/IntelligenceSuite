"""Server RAG per DocIntelligence."""

from __future__ import annotations
import uvicorn

from intelligence_core.retriever import Retriever
from intelligence_core.store import ChromaStore
from intelligence_core.embedder import get_embedder
from intelligence_core.server_base import create_app
from intelligence_core.config import settings


def build_app():
    store = ChromaStore(collection_name="doc_intelligence")
    retriever = Retriever(embedder=get_embedder(), store=store)
    return create_app(title="DocIntelligence RAG Server", retriever=retriever)


app = build_app()


def main():
    uvicorn.run(
        "DocIntelligence.doc_server:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
