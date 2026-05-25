"""Server RAG per CodeIntelligence — monta intelligence_core.server_base."""

from __future__ import annotations
import uvicorn

from intelligence_core.retriever import Retriever
from intelligence_core.server_base import create_app
from intelligence_core.config import settings


def build_app():
    retriever = Retriever.load_default()
    return create_app(title="CodeIntelligence RAG Server", retriever=retriever)


app = build_app()


def main():
    uvicorn.run(
        "CodeIntelligence.rag_server:app",
        host=settings.api_host,
        port=settings.ci_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
