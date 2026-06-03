"""Test del caching di generate_testset: --samples tronca senza rigenerare.

Esercita solo il ramo "cache hit" → nessuna dipendenza RAGAS/langchain.
"""

from __future__ import annotations

import json
import os

import pytest

from intelligence_core.evaluation.generator import generate_testset


def _write_cache(base, domain, n):
    d = base / "tests" / "eval"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{domain}_testset.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for i in range(n):
            f.write(json.dumps({"question": f"q{i}", "ground_truth": f"a{i}"}) + "\n")
    return path


@pytest.fixture
def _in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # cache_path è relativa alla CWD
    return tmp_path


def test_samples_truncates_cached_testset(_in_tmp):
    _write_cache(_in_tmp, "code", n=50)
    rows = generate_testset(domain="code", test_size=10)
    assert len(rows) == 10
    assert [r["question"] for r in rows] == [f"q{i}" for i in range(10)]


def test_samples_equal_to_cache_returns_all(_in_tmp):
    _write_cache(_in_tmp, "code", n=8)
    rows = generate_testset(domain="code", test_size=8)
    assert len(rows) == 8


def test_request_more_than_cache_returns_available(_in_tmp):
    # Senza --regenerate non possiamo crearne di più: torna quel che c'è.
    _write_cache(_in_tmp, "code", n=5)
    rows = generate_testset(domain="code", test_size=20)
    assert len(rows) == 5
