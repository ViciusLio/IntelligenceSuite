"""Shared pytest fixtures for the IntelligenceSuite test suite.

The KPI fixtures here mount a **disk-less, in-memory ChromaDB** (`:memory:`),
load versioned synthetic fixtures from ``tests/fixtures/``, and return a ready
``Retriever`` — so retrieval-quality (KPI) tests run deterministically in CI
without Ollama, without any optional extra, and without touching disk.

Embeddings come from :class:`HashingEmbedder`, a dependency-free bag-of-words
embedder: cosine similarity between query and chunk reflects their lexical
overlap. The synthetic fixtures are written so each question shares its
distinctive terms with exactly one target chunk; if the store/retriever wiring
breaks, retrieval breaks and the KPI tests fail for real.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Embedding dimensionality for the deterministic test embedder. Large enough to
# keep hash collisions between the small synthetic vocabulary negligible.
_EMBED_DIM = 512

# Very common English words carry no retrieval signal — drop them so similarity
# is driven by the distinctive terms shared between a query and its chunk.
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "into", "are", "was",
    "how", "what", "which", "does", "use", "used", "when", "where", "via", "you",
    "your", "our", "per", "out", "its", "has", "have", "between", "over", "under",
})


def _tokens(text: str) -> list[str]:
    return [
        w for w in re.findall(r"[a-z0-9]+", text.lower())
        if len(w) > 2 and w not in _STOPWORDS
    ]


class HashingEmbedder:
    """Deterministic, offline bag-of-words embedder (Embedder protocol).

    Each token is hashed into a fixed-width vector; the L2-normalised result
    makes cosine similarity equal lexical overlap. No network, no model
    download, fully reproducible across machines and Python runs.
    """

    def embed_one(self, text: str) -> list[float]:
        vec = [0.0] * _EMBED_DIM
        for tok in _tokens(text):
            idx = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16) % _EMBED_DIM
            vec[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


def _load_fixture(name: str) -> list[dict]:
    with (FIXTURES_DIR / name).open(encoding="utf-8") as f:
        return json.load(f)


def _build_in_memory_retriever(chunks: list[dict], domain: str):
    """Embed *chunks* with HashingEmbedder and load them into an in-memory store.

    Uses the Fase-1 collection naming (``paths.collection_name(domain)``) so the
    KPI tests exercise the same naming path as production — with the default
    project this is the classic ``code_intelligence`` / ``doc_intelligence``.
    """
    from intelligence_core import paths
    from intelligence_core.retriever import Retriever
    from intelligence_core.store import ChromaStore

    embedder = HashingEmbedder()
    enriched = [dict(c, embedding=embedder.embed_one(c["text"])) for c in chunks]

    store = ChromaStore(
        collection_name=paths.collection_name(domain),
        persist_dir=":memory:",
    )
    store.add(enriched)
    return Retriever(embedder=embedder, store=store)


@pytest.fixture
def hashing_embedder() -> HashingEmbedder:
    return HashingEmbedder()


@pytest.fixture
def kpi_qa() -> list[dict]:
    """Synthetic question → expected-chunk-id pairs (code + doc)."""
    return _load_fixture("kpi_qa.json")


@pytest.fixture
def kpi_code_retriever():
    """Retriever over synthetic code chunks on an in-memory ChromaDB."""
    return _build_in_memory_retriever(_load_fixture("kpi_code_chunks.json"), "code")


@pytest.fixture
def kpi_doc_retriever():
    """Retriever over synthetic doc chunks on an in-memory ChromaDB."""
    return _build_in_memory_retriever(_load_fixture("kpi_doc_chunks.json"), "doc")
