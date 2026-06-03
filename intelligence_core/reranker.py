"""Cross-encoder reranker: riordina i candidati prima del taglio a top_k.

La vector search è un bi-encoder (query e chunk embeddati separatamente): veloce
ma impreciso. Un cross-encoder valuta la coppia (query, chunk) insieme, quindi
discrimina molto meglio la pertinenza — leva principale per ``context_precision``.

Attivabile via ``RERANK_ENABLED=true``. Richiede l'extra ``[st]``
(sentence-transformers). Se il modello non è disponibile, ``get_reranker`` ritorna
``None`` e il retriever ricade sul comportamento legacy (keyword boost).
"""

from __future__ import annotations

import logging
import math
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class Reranker(Protocol):
    def rerank(self, query: str, chunks: list[dict], top_k: int) -> list[dict]: ...


class CrossEncoderReranker:
    """Riordina i chunk con un cross-encoder di sentence-transformers.

    Lo score del cross-encoder è un logit grezzo: lo normalizziamo con una
    sigmoid in ``[0, 1]`` per restare coerenti con la scala coseno usata a valle
    (confidence / soglia di escalation).
    """

    def __init__(self, model_name: str | None = None):
        from intelligence_core.config import settings

        _model_name = model_name or settings.rerank_model
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(_model_name)
            logger.info("CrossEncoderReranker: loaded model '%s'", _model_name)
        except ImportError as exc:
            raise ImportError(
                f"sentence-transformers failed to load: {exc}\n"
                "Reranking richiede l'extra: pip install 'intelligence-suite[st]'"
            ) from exc

    def rerank(self, query: str, chunks: list[dict], top_k: int) -> list[dict]:
        if not chunks:
            return []
        pairs = [(query, c.get("text", "")) for c in chunks]
        raw_scores = self._model.predict(pairs)
        for chunk, raw in zip(chunks, raw_scores):
            chunk["score"] = _sigmoid(float(raw))
        chunks.sort(key=lambda c: c["score"], reverse=True)
        return chunks[:top_k]


def _sigmoid(x: float) -> float:
    # Clamp per evitare overflow di math.exp su logit estremi.
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-min(x, 60.0)))
    e = math.exp(max(x, -60.0))
    return e / (1.0 + e)


_RERANKER_CACHE: Reranker | None = None
_RERANKER_TRIED: bool = False


def get_reranker() -> Reranker | None:
    """Factory cachata. Ritorna ``None`` se disabilitato o non disponibile.

    Il modello viene caricato una sola volta per processo; un fallimento
    (extra mancante) viene loggato e disabilita il reranking senza rompere
    il retrieval.
    """
    global _RERANKER_CACHE, _RERANKER_TRIED
    from intelligence_core.config import settings

    if not settings.rerank_enabled:
        return None
    if _RERANKER_TRIED:
        return _RERANKER_CACHE

    _RERANKER_TRIED = True
    try:
        _RERANKER_CACHE = CrossEncoderReranker()
    except Exception as exc:  # noqa: BLE001 — degradazione controllata
        logger.warning(
            "Reranking disabilitato: impossibile caricare il cross-encoder (%s). "
            "Fallback al keyword boost.",
            exc,
        )
        _RERANKER_CACHE = None
    return _RERANKER_CACHE
