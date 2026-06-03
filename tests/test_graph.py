"""Tests for the NetworkX dependency graph (build, persist, query, GraphRAG)."""

from __future__ import annotations

import json

import networkx as nx
import pytest

# intelligence_core imports are deferred into functions/fixtures: importing the
# package at collection time triggers config.Settings() under a module identity
# that pydantic-settings rejects when this file is collected in isolation.


# ── Fixtures ──────────────────────────────────────────────────────────────────

SYNTHETIC_CHUNKS = [
    {
        "id": "code::function::a.py::alpha",
        "type": "function",
        "domain": "code",
        "source": "a.py",
        "text": "def alpha(): ...",
        "metadata": {"name": "alpha", "line_start": 1, "calls": ["beta", "gamma"]},
    },
    {
        "id": "code::function::a.py::beta",
        "type": "function",
        "domain": "code",
        "source": "a.py",
        "text": "def beta(): ...",
        "metadata": {"name": "beta", "line_start": 10, "calls": ["gamma"]},
    },
    {
        "id": "code::function::b.py::gamma",
        "type": "function",
        "domain": "code",
        "source": "b.py",
        "text": "def gamma(): ...",
        "metadata": {"name": "gamma", "line_start": 1, "calls": []},
    },
    {
        "id": "code::class::b.py::Base",
        "type": "class",
        "domain": "code",
        "source": "b.py",
        "text": "class Base: ...",
        "metadata": {"name": "Base", "line_start": 20, "bases": []},
    },
    {
        "id": "code::class::c.py::Derived",
        "type": "class",
        "domain": "code",
        "source": "c.py",
        "text": "class Derived(Base): ...",
        "metadata": {"name": "Derived", "line_start": 1, "bases": ["Base"]},
    },
    {
        # Non-graph type — must be ignored.
        "id": "code::comment::c.py::note",
        "type": "comment",
        "domain": "code",
        "source": "c.py",
        "text": "# note",
        "metadata": {},
    },
]


@pytest.fixture()
def chunks_file(tmp_path, monkeypatch):
    from intelligence_core.graph import builder
    path = tmp_path / "chunks.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for c in SYNTHETIC_CHUNKS:
            f.write(json.dumps(c) + "\n")
    monkeypatch.setattr(builder, "_get_chunks_path", lambda domain: path)
    return path


@pytest.fixture()
def built_graph(chunks_file):
    from intelligence_core.graph import builder
    return builder.build_graph("code")


# ── build_graph ─────────────────────────────────────────────────────────────

def test_build_graph_nodes_exclude_non_graph_types(built_graph):
    assert built_graph.number_of_nodes() == 5
    assert "code::comment::c.py::note" not in built_graph


def test_build_graph_calls_edges(built_graph):
    alpha = "code::function::a.py::alpha"
    beta = "code::function::a.py::beta"
    gamma = "code::function::b.py::gamma"
    assert built_graph.edges[alpha, beta]["relation"] == "CALLS"
    assert built_graph.edges[alpha, gamma]["relation"] == "CALLS"
    assert built_graph.edges[beta, gamma]["relation"] == "CALLS"


def test_build_graph_inherits_edge(built_graph):
    derived = "code::class::c.py::Derived"
    base = "code::class::b.py::Base"
    assert built_graph.edges[derived, base]["relation"] == "INHERITS_FROM"


def test_build_graph_node_attributes(built_graph):
    data = built_graph.nodes["code::function::b.py::gamma"]
    assert data["name"] == "gamma"
    assert data["file"] == "b.py"
    assert data["type"] == "function"


def test_build_graph_missing_chunks_raises(tmp_path, monkeypatch):
    from intelligence_core.graph import builder
    monkeypatch.setattr(
        builder, "_get_chunks_path", lambda domain: tmp_path / "nope.jsonl"
    )
    with pytest.raises(FileNotFoundError):
        builder.build_graph("code")


def test_name_from_id():
    from intelligence_core.graph import builder
    assert builder._name_from_id("code::function::a.py::alpha") == "alpha"
    assert builder._name_from_id("simple") == "simple"


# ── store: save / load / exists ───────────────────────────────────────────────

def test_save_and_load_roundtrip(built_graph, tmp_path, monkeypatch):
    from intelligence_core.graph import store
    monkeypatch.setattr(store, "GRAPH_DIR", tmp_path)
    assert not store.graph_exists("code")
    store.save_graph(built_graph, "code")
    assert store.graph_exists("code")
    loaded = store.load_graph("code")
    assert isinstance(loaded, nx.DiGraph)
    assert loaded.number_of_nodes() == built_graph.number_of_nodes()
    assert loaded.number_of_edges() == built_graph.number_of_edges()


def test_load_graph_missing_raises(tmp_path, monkeypatch):
    from intelligence_core.graph import store
    monkeypatch.setattr(store, "GRAPH_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        store.load_graph("code")


# ── GraphRetriever ─────────────────────────────────────────────────────────────

@pytest.fixture()
def retriever(built_graph):
    from intelligence_core.graph.retriever import GraphRetriever
    r = GraphRetriever("code")
    r._graph = built_graph
    return r


def test_find_node(retriever):
    assert retriever.find_node("gamma") == "code::function::b.py::gamma"
    assert retriever.find_node("missing") is None


def test_who_calls_direct(retriever):
    callers = retriever.who_calls("gamma", depth=1)
    names = {c["name"] for c in callers}
    assert names == {"alpha", "beta"}


def test_impact_analysis(retriever):
    result = retriever.impact_analysis("gamma", depth=3)
    assert result["function"] == "gamma"
    assert result["total_affected"] == 2
    assert set(result["affected_files"]) == {"a.py"}
    assert result["risk_level"] == "low"


def test_impact_analysis_unknown(retriever):
    result = retriever.impact_analysis("ghost")
    assert "error" in result


def test_dependencies_of(retriever):
    deps = retriever.dependencies_of("alpha", depth=2)
    names = {d["name"] for d in deps}
    assert "beta" in names and "gamma" in names


def test_most_connected(retriever):
    top = retriever.most_connected(top_k=1)
    assert top[0]["name"] == "gamma"
    assert top[0]["in_degree"] == 2


def test_expand_context(retriever):
    alpha = "code::function::a.py::alpha"
    extra = retriever.expand_context([alpha], depth=1)
    assert "code::function::a.py::beta" in extra
    assert alpha not in extra


def test_expand_context_unknown_id(retriever):
    assert retriever.expand_context(["does-not-exist"]) == []


def test_risk_level():
    from intelligence_core.graph.retriever import _risk_level
    assert _risk_level(0) == "none"
    assert _risk_level(2) == "low"
    assert _risk_level(7) == "medium"
    assert _risk_level(50) == "high"
