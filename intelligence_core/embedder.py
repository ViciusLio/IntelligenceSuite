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
        except Exception as exc:
            raise RuntimeError(
                f"OllamaEmbedder: cannot reach {self.base_url} (model={self.model}).\n"
                f"  Fix 1: ollama serve && ollama pull {self.model}\n"
                f"  Fix 2: set EMBED_BACKEND=st in .env (offline, no server required)\n"
                f"  Original error: {exc}"
            ) from exc

    def embed_one(self, text: str) -> list[float]:
        return self._embed_single(text)


class SentenceTransformerEmbedder:
    """CPU-only offline embedder via sentence-transformers.

    Model is controlled by ``ST_MODEL`` in .env (or the ``model_name`` argument).

    Recommended models:
        - ``all-MiniLM-L6-v2``                        English only, fast (default)
        - ``paraphrase-multilingual-MiniLM-L12-v2``   50+ languages, same speed
        - ``paraphrase-multilingual-mpnet-base-v2``   50+ languages, higher quality
    """

    def __init__(self, model_name: str = None):
        from intelligence_core.config import settings
        _model_name = model_name or settings.st_model
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(_model_name)
            logger.info("SentenceTransformerEmbedder: loaded model '%s'", _model_name)
        except ImportError as exc:
            raise ImportError(
                f"sentence-transformers failed to load: {exc}\n"
                "If not installed: pip install 'intelligence-suite[st]'\n"
                "If already installed, check for NumPy/scipy DLL conflicts "
                "(try: conda install numpy scipy --force-reinstall)"
            ) from exc

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


def get_embedder(backend: str = None, *, model: str = None) -> Embedder:
    """Factory: crea l'embedder appropriato in base a settings.embed_backend.

    Args:
        backend: Override ``EMBED_BACKEND`` (``"ollama"`` | ``"st"`` | ``"claude"``).
        model:   Override del nome modello (``ST_MODEL`` / ``OLLAMA_EMBED_MODEL``).
                 Ignorato dal backend ``claude`` (modello fisso voyage).
    """
    from intelligence_core.config import settings
    backend = backend or settings.embed_backend

    if backend in ("st", "sentence_transformer"):
        return SentenceTransformerEmbedder(model_name=model)   # None → settings.st_model
    if backend == "claude":
        return ClaudeEmbedder()
    return OllamaEmbedder(model=model)   # None → settings.ollama_embed_model


def get_module_embedder(module: str) -> Embedder:
    """Embedder per uno specifico modulo, applicando gli override per-modulo.

    Prefissi modulo
    ---------------
    "pi" → ProposalIntelligence (PI_EMBED_BACKEND, PI_EMBED_MODEL)

    Qualsiasi variabile lasciata vuota ricade sui valori globali
    ``EMBED_BACKEND`` / ``ST_MODEL``. Permette, per esempio, di usare un
    embedder multilingue solo per il modulo Q&A senza re-indicizzare le altre
    collezioni (che restano sull'embedder globale).
    """
    from intelligence_core.config import settings

    prefix  = module.lower()
    backend = getattr(settings, f"{prefix}_embed_backend", "") or None
    model   = getattr(settings, f"{prefix}_embed_model",   "") or None

    if backend or model:
        logger.info(
            "Module [%s] embedder override → backend=%s  model=%s",
            module.upper(), backend or "(global)", model or "(global)",
        )

    return get_embedder(backend, model=model)
