"""Embedder: Ollama, SentenceTransformer e Claude — factory via settings."""

from __future__ import annotations
import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_one(self, text: str) -> list[float]: ...


class OllamaEmbedder:
    """Chiama Ollama /api/embeddings. Fallback a vettore di zeri se non disponibile."""

    def __init__(self, base_url: str = None, model: str = None):
        from intelligence_core.config import settings
        self.base_url = base_url or settings.ollama_base_url
        self.model = model or settings.ollama_embed_model

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx
        results = []
        for text in texts:
            results.append(self._embed_single(text))
        return results

    def _embed_single(self, text: str) -> list[float]:
        import httpx
        try:
            resp = httpx.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
        except Exception as e:
            logger.error(
                "OllamaEmbedder: cannot reach %s (model=%s) — returning zero vector.\n"
                "  Fix: ollama serve && ollama pull %s\n"
                "  Or switch: EMBED_BACKEND=st in .env (no server required)",
                self.base_url, self.model, self.model,
            )
            return [0.0] * 384

    def embed_one(self, text: str) -> list[float]:
        return self._embed_single(text)


class SentenceTransformerEmbedder:
    """Usa all-MiniLM-L6-v2 offline. Richiede sentence-transformers installato."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name)
        except ImportError:
            raise ImportError(
                "sentence-transformers non installato. "
                "Esegui: pip install sentence-transformers"
            )

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, convert_to_numpy=True).tolist()

    def embed_one(self, text: str) -> list[float]:
        return self._model.encode([text], convert_to_numpy=True)[0].tolist()


class ClaudeEmbedder:
    """Usa voyage-code-2 per code, voyage-3 per doc. Richiede ANTHROPIC_API_KEY."""

    def __init__(self, domain: str = "code"):
        from intelligence_core.config import settings
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY non configurata")
        self.api_key = settings.anthropic_api_key
        self.model = "voyage-code-2" if domain == "code" else "voyage-3"

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx
        results = []
        for text in texts:
            results.append(self.embed_one(text))
        return results

    def embed_one(self, text: str) -> list[float]:
        import httpx
        resp = httpx.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


def get_embedder(backend: str = None) -> Embedder:
    """Factory: crea l'embedder appropriato in base a settings.embed_backend."""
    from intelligence_core.config import settings
    backend = backend or settings.embed_backend

    if backend == "sentence_transformer":
        return SentenceTransformerEmbedder()
    if backend == "claude":
        return ClaudeEmbedder()
    return OllamaEmbedder()
