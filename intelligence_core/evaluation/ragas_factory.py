"""Costruisce LLM ed embeddings per RAGAS dalle settings del progetto.

RAGAS (testset generation + metriche) richiede un LLM e un embedder.
Li cabliamo sul vLLM/OpenAI-compatibile configurato in settings, così la
valutazione usa lo stesso backend del sistema reale invece di OpenAI cloud.
"""

from __future__ import annotations


def get_ragas_llm():
    """LangchainLLMWrapper sul backend OpenAI-compatibile (vLLM) delle settings."""
    from langchain_openai import ChatOpenAI
    from ragas.llms import LangchainLLMWrapper

    from intelligence_core.config import settings

    chat = ChatOpenAI(
        model=settings.openai_model,
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key or "EMPTY",
        temperature=0.0,
    )
    return LangchainLLMWrapper(chat)


def get_ragas_embeddings():
    """LangchainEmbeddingsWrapper su un adapter dell'embedder del progetto."""
    from ragas.embeddings import LangchainEmbeddingsWrapper

    from intelligence_core.embedder import get_embedder

    return LangchainEmbeddingsWrapper(_ProjectEmbeddings(get_embedder()))


class _ProjectEmbeddings:
    """Adapter: espone l'Embedder del progetto come langchain Embeddings."""

    def __init__(self, embedder):
        self._embedder = embedder

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.embed(list(texts))

    def embed_query(self, text: str) -> list[float]:
        return self._embedder.embed_one(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)
