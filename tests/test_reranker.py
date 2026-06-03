"""Test del cross-encoder reranker e dell'integrazione nel Retriever.

Usano fake/monkeypatch: non richiedono sentence-transformers installato.
"""

from __future__ import annotations

import pytest

import intelligence_core.reranker as reranker_mod
from intelligence_core.reranker import CrossEncoderReranker, _sigmoid, get_reranker
from intelligence_core.retriever import MultiRetriever, Retriever


# ── _sigmoid ────────────────────────────────────────────────────────────────
def test_sigmoid_midpoint_and_bounds():
    assert _sigmoid(0.0) == pytest.approx(0.5)
    assert 0.99 < _sigmoid(100.0) <= 1.0
    assert 0.0 <= _sigmoid(-100.0) < 0.01


# ── CrossEncoderReranker.rerank ───────────────────────────────────────────────
class _FakeModel:
    def __init__(self, scores):
        self._scores = scores

    def predict(self, pairs):
        assert len(pairs) == len(self._scores)
        return self._scores


def _reranker_with(scores) -> CrossEncoderReranker:
    r = CrossEncoderReranker.__new__(CrossEncoderReranker)  # bypass __init__/import
    r._model = _FakeModel(scores)
    return r


def test_rerank_reorders_by_model_score_and_truncates():
    r = _reranker_with([0.1, 5.0, -2.0])
    chunks = [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}, {"id": "c", "text": "z"}]
    out = r.rerank("q", chunks, top_k=2)
    assert [c["id"] for c in out] == ["b", "a"]  # 5.0 > 0.1 > -2.0
    assert all(0.0 <= c["score"] <= 1.0 for c in out)


def test_rerank_empty_returns_empty():
    assert _reranker_with([]).rerank("q", [], top_k=5) == []


# ── get_reranker factory ──────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _reset_reranker_cache():
    reranker_mod._RERANKER_CACHE = None
    reranker_mod._RERANKER_TRIED = False
    yield
    reranker_mod._RERANKER_CACHE = None
    reranker_mod._RERANKER_TRIED = False


def test_get_reranker_disabled_returns_none(monkeypatch):
    from intelligence_core.config import settings

    monkeypatch.setattr(settings, "rerank_enabled", False)
    assert get_reranker() is None


def test_get_reranker_handles_load_failure_gracefully(monkeypatch):
    from intelligence_core.config import settings

    monkeypatch.setattr(settings, "rerank_enabled", True)

    def _boom(*a, **k):
        raise ImportError("sentence-transformers mancante")

    monkeypatch.setattr(reranker_mod, "CrossEncoderReranker", _boom)
    assert get_reranker() is None  # degradazione controllata, nessuna eccezione


# ── Retriever integration ─────────────────────────────────────────────────────
class _FakeEmbedder:
    def embed_one(self, text):
        return [0.0, 0.0]


class _FakeStore:
    def __init__(self, chunks):
        self._chunks = chunks
        self.last_top_k = None

    def search(self, embedding, top_k, filters=None):
        self.last_top_k = top_k
        return [dict(c) for c in self._chunks[:top_k]]


class _ReverseReranker:
    """Inverte l'ordine così è ovvio che è stato lui a riordinare."""

    def rerank(self, query, chunks, top_k):
        for c in chunks:
            c["score"] = 1.0
        return list(reversed(chunks))[:top_k]


def _chunks(n):
    return [{"id": str(i), "text": f"term{i} body", "score": 0.0} for i in range(n)]


def test_search_uses_reranker_and_widens_candidate_pool(monkeypatch):
    store = _FakeStore(_chunks(30))
    r = Retriever(embedder=_FakeEmbedder(), store=store)
    monkeypatch.setattr("intelligence_core.reranker.get_reranker", lambda: _ReverseReranker())

    results = r.search("term0", top_k=5, domain=None)

    assert store.last_top_k == 20  # max(top_k*2=10, rerank_candidates=20)
    assert len(results) == 5
    assert results[0].chunk["id"] == "19"  # reranker ha invertito i 20 candidati
    assert results[0].rank == 1


def test_search_falls_back_to_keyword_when_no_reranker(monkeypatch):
    store = _FakeStore(_chunks(30))
    r = Retriever(embedder=_FakeEmbedder(), store=store)
    monkeypatch.setattr("intelligence_core.reranker.get_reranker", lambda: None)

    results = r.search("term3 term7", top_k=5, domain=None)

    assert store.last_top_k == 10  # top_k*2, nessun allargamento del pool
    assert len(results) == 5
    # I chunk che contengono i termini di query ricevono il boost e salgono.
    top_ids = {res.chunk["id"] for res in results}
    assert "3" in top_ids and "7" in top_ids


# ── MultiRetriever (eval --domain all) ────────────────────────────────────────
def _tagged_chunks(prefix, n):
    return [
        {"id": f"{prefix}-{i}", "text": f"{prefix} term{i}", "score": 0.0}
        for i in range(n)
    ]


def test_multiretriever_pools_all_collections_and_reranks(monkeypatch):
    code = _FakeStore(_tagged_chunks("code", 6))
    doc = _FakeStore(_tagged_chunks("doc", 6))
    mentor = _FakeStore(_tagged_chunks("mentor", 6))
    mr = MultiRetriever(embedder=_FakeEmbedder(), stores=[code, doc, mentor])
    monkeypatch.setattr("intelligence_core.reranker.get_reranker", lambda: _ReverseReranker())

    results = mr.search("term0", top_k=4)

    # Ogni store interrogato col pool allargato (max(top_k*2=8, candidates=20)=20)
    assert code.last_top_k == doc.last_top_k == mentor.last_top_k == 20
    assert len(results) == 4
    # Il pool fuso contiene chunk di domini diversi: la classifica è globale.
    prefixes = {res.chunk["id"].split("-")[0] for res in results}
    assert prefixes <= {"code", "doc", "mentor"}
    assert results[0].rank == 1


def test_multiretriever_survives_failing_store(monkeypatch):
    class _BoomStore:
        def search(self, embedding, top_k, filters=None):
            raise RuntimeError("collection assente")

    ok = _FakeStore(_tagged_chunks("code", 5))
    mr = MultiRetriever(embedder=_FakeEmbedder(), stores=[_BoomStore(), ok])
    monkeypatch.setattr("intelligence_core.reranker.get_reranker", lambda: None)

    results = mr.search("term1", top_k=3)

    assert len(results) == 3  # lo store rotto è ignorato, l'altro risponde
    assert all(res.chunk["id"].startswith("code") for res in results)
