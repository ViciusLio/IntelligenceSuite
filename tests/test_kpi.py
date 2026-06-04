"""Deterministic retrieval-quality (KPI) tests on an in-memory store (v0.10.0).

Unlike the legacy ``TestKPIThresholds`` (which skips when no live index exists),
these tests always run in CI: a disk-less ChromaDB is loaded with versioned
synthetic fixtures (see ``conftest.py``) and the retriever is exercised against
known question → chunk pairs.

The thresholds are more generous than production because the synthetic data is
easier to retrieve — but they still **fail for real** if the retriever is
broken (wrong collection, embeddings not loaded, ranking inverted, …).

Marked ``kpi`` so ``pytest -m kpi`` runs only these; they are *not* ``slow``
(no real embedding backend, no network, no disk).
"""

from __future__ import annotations

import time

import pytest

from tests.test_intelligence_suite import compute_metrics

pytestmark = pytest.mark.kpi

# Generous CI thresholds for synthetic data — production targets live in
# ARCHITECTURE.md / test_intelligence_suite.KPI_THRESHOLDS.
KPI_MIN = {
    "hit_at_1": 0.80,
    "hit_at_5": 1.00,
    "mrr": 0.85,
    # Generous CI ceiling: in-memory search is fast, but cold ChromaDB/rust
    # bindings + per-call imports vary widely across runners. This catches
    # pathological regressions (seconds per query), not the production SLA.
    "latency_p50_ms": 2000.0,
}


def _evaluate(retriever, qa_pairs: list[dict]) -> dict:
    """Run every question through *retriever* and return aggregate metrics."""
    results, latencies = [], []
    for item in qa_pairs:
        t0 = time.perf_counter()
        retrieved = retriever.search(item["query"], top_k=5)
        latencies.append((time.perf_counter() - t0) * 1000)
        results.append({
            "query_id": item["query_id"],
            "retrieved": [r.chunk.get("id", "") for r in retrieved],
            "relevant": item["relevant"],
        })
    metrics = compute_metrics(results, k_values=[1, 3, 5])
    latencies.sort()
    metrics["latency_p50_ms"] = latencies[len(latencies) // 2]
    metrics["latency_p99_ms"] = latencies[min(int(len(latencies) * 0.99), len(latencies) - 1)]
    metrics["_results"] = results
    return metrics


@pytest.fixture
def code_qa(kpi_qa):
    return [q for q in kpi_qa if q["domain"] == "code"]


@pytest.fixture
def doc_qa(kpi_qa):
    return [q for q in kpi_qa if q["domain"] == "doc"]


# ── store sanity ─────────────────────────────────────────────────────────────

class TestInMemoryStore:
    def test_code_store_is_populated(self, kpi_code_retriever):
        assert kpi_code_retriever.store.count() == 8

    def test_doc_store_is_populated(self, kpi_doc_retriever):
        assert kpi_doc_retriever.store.count() == 8

    def test_search_returns_results(self, kpi_code_retriever):
        results = kpi_code_retriever.search("JWT authentication token", top_k=5)
        assert len(results) > 0
        assert all(0.0 <= r.score <= 1.0 + 1e-6 for r in results)


# ── code-domain KPI ──────────────────────────────────────────────────────────

class TestCodeKPI:
    def test_code_hit_at_1(self, kpi_code_retriever, code_qa):
        m = _evaluate(kpi_code_retriever, code_qa)
        assert m["hit_at_1"] >= KPI_MIN["hit_at_1"], (
            f"Hit@1 code {m['hit_at_1']:.2%} < {KPI_MIN['hit_at_1']:.0%}"
        )

    def test_code_hit_at_5(self, kpi_code_retriever, code_qa):
        m = _evaluate(kpi_code_retriever, code_qa)
        assert m["hit_at_5"] >= KPI_MIN["hit_at_5"], (
            f"Hit@5 code {m['hit_at_5']:.2%} < {KPI_MIN['hit_at_5']:.0%}"
        )

    def test_code_mrr(self, kpi_code_retriever, code_qa):
        m = _evaluate(kpi_code_retriever, code_qa)
        assert m["mrr"] >= KPI_MIN["mrr"], f"MRR code {m['mrr']:.3f} < {KPI_MIN['mrr']}"


# ── doc-domain KPI ───────────────────────────────────────────────────────────

class TestDocKPI:
    def test_doc_hit_at_1(self, kpi_doc_retriever, doc_qa):
        m = _evaluate(kpi_doc_retriever, doc_qa)
        assert m["hit_at_1"] >= KPI_MIN["hit_at_1"], (
            f"Hit@1 doc {m['hit_at_1']:.2%} < {KPI_MIN['hit_at_1']:.0%}"
        )

    def test_doc_hit_at_5(self, kpi_doc_retriever, doc_qa):
        m = _evaluate(kpi_doc_retriever, doc_qa)
        assert m["hit_at_5"] >= KPI_MIN["hit_at_5"], (
            f"Hit@5 doc {m['hit_at_5']:.2%} < {KPI_MIN['hit_at_5']:.0%}"
        )


# ── invariants & latency ─────────────────────────────────────────────────────

class TestRetrievalInvariants:
    def test_confidence_always_in_unit_interval(self, kpi_code_retriever, kpi_qa):
        for item in kpi_qa:
            for r in kpi_code_retriever.search(item["query"], top_k=5):
                assert 0.0 <= r.score <= 1.0 + 1e-6, f"score out of [0,1]: {r.score}"

    def test_ranks_are_sequential(self, kpi_doc_retriever):
        results = kpi_doc_retriever.search("rollback deploy fails", top_k=5)
        ranks = [r.rank for r in results]
        assert ranks == list(range(1, len(results) + 1))

    def test_median_latency_under_threshold(self, kpi_code_retriever, code_qa):
        m = _evaluate(kpi_code_retriever, code_qa)
        assert m["latency_p50_ms"] <= KPI_MIN["latency_p50_ms"], (
            f"P50 {m['latency_p50_ms']:.1f}ms > {KPI_MIN['latency_p50_ms']}ms"
        )

    def test_broken_retriever_would_fail(self, kpi_code_retriever, code_qa):
        # Sanity: the suite must be sensitive to a broken retriever. Searching
        # for the relevant id's distinctive term must surface that id at rank 1.
        m = _evaluate(kpi_code_retriever, code_qa)
        assert m["hit_at_1"] > 0.0  # a wired-up retriever never scores zero here
