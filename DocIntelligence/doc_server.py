"""Server RAG per DocIntelligence."""

from __future__ import annotations
import uvicorn

from intelligence_core.retriever import Retriever
from intelligence_core.store import ChromaStore
from intelligence_core.embedder import get_embedder
from intelligence_core.server_base import create_app
from intelligence_core.config import settings
from intelligence_core.llm import get_module_llm_provider


def build_app():
    from intelligence_core import paths
    store = ChromaStore(collection_name=paths.collection_name("doc"),
                        persist_dir=str(paths.chroma_dir()))
    retriever = Retriever(embedder=get_embedder(), store=store)
    return create_app(
        title="DocIntelligence RAG Server",
        retriever=retriever,
        module="doc",
        llm_provider=get_module_llm_provider("di"),
    )


app = build_app()


def main():
    uvicorn.run(
        "DocIntelligence.doc_server:app",
        host=settings.api_host,
        port=settings.di_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
