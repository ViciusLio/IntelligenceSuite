"""Tests for IS_PROJECT multi-tenancy namespacing (FASE 1 — v0.9.0)."""

from __future__ import annotations

import pytest
from pathlib import Path


# ── helpers ───────────────────────────────────────────────────────────────────

def _set_project(monkeypatch, value: str):
    """Override settings.is_project without touching environment variables."""
    from intelligence_core.config import settings
    monkeypatch.setattr(settings, "is_project", value)


# ── paths.py ─────────────────────────────────────────────────────────────────

class TestPaths:
    def test_default_collection_name_unchanged(self, monkeypatch):
        _set_project(monkeypatch, "default")
        from intelligence_core import paths
        assert paths.collection_name("code")   == "code_intelligence"
        assert paths.collection_name("doc")    == "doc_intelligence"
        assert paths.collection_name("mentor") == "mentor_intelligence"
        assert paths.collection_name("qa")     == "proposal_intelligence"

    def test_project_collection_name_prefixed(self, monkeypatch):
        _set_project(monkeypatch, "acme")
        from intelligence_core import paths
        assert paths.collection_name("code")   == "acme_code_intelligence"
        assert paths.collection_name("doc")    == "acme_doc_intelligence"
        assert paths.collection_name("mentor") == "acme_mentor_intelligence"
        assert paths.collection_name("qa")     == "acme_proposal_intelligence"

    def test_unknown_domain_passthrough(self, monkeypatch):
        _set_project(monkeypatch, "demo")
        from intelligence_core import paths
        assert paths.collection_name("custom") == "demo_custom"

    def test_default_state_dir_is_base(self, monkeypatch):
        _set_project(monkeypatch, "default")
        from intelligence_core import paths
        assert paths.state_dir() == Path.home() / ".intelligence_suite"

    def test_project_state_dir_is_subdirectory(self, monkeypatch):
        _set_project(monkeypatch, "acme")
        from intelligence_core import paths
        assert paths.state_dir() == Path.home() / ".intelligence_suite" / "acme"

    def test_default_chroma_dir_honours_settings(self, monkeypatch):
        _set_project(monkeypatch, "default")
        from intelligence_core import paths
        from intelligence_core.config import settings
        assert paths.chroma_dir() == Path(settings.chroma_persist_dir)

    def test_project_chroma_dir_under_state(self, monkeypatch):
        _set_project(monkeypatch, "acme")
        from intelligence_core import paths
        assert paths.chroma_dir() == Path.home() / ".intelligence_suite" / "acme" / "chroma"

    def test_graph_dir(self, monkeypatch):
        _set_project(monkeypatch, "acme")
        from intelligence_core import paths
        assert paths.graph_dir() == Path.home() / ".intelligence_suite" / "acme" / "graph"

    def test_eval_dir(self, monkeypatch):
        _set_project(monkeypatch, "acme")
        from intelligence_core import paths
        assert paths.eval_dir() == Path.home() / ".intelligence_suite" / "acme" / "eval"

    def test_skill_sessions_dir(self, monkeypatch):
        _set_project(monkeypatch, "acme")
        from intelligence_core import paths
        assert paths.skill_sessions_dir() == (
            Path.home() / ".intelligence_suite" / "acme" / "skill_sessions"
        )


# ── graph/store.py ────────────────────────────────────────────────────────────

class TestGraphStore:
    def test_graph_exists_uses_project_dir(self, monkeypatch, tmp_path):
        _set_project(monkeypatch, "acme")
        from intelligence_core.graph import store
        monkeypatch.setattr(store, "GRAPH_DIR", tmp_path)
        assert store.graph_exists("code") is False
        (tmp_path / "code_graph.json").write_text("{}", encoding="utf-8")
        assert store.graph_exists("code") is True

    def test_graph_dir_sentinel_none_delegates_to_paths(self, monkeypatch):
        _set_project(monkeypatch, "testproject")
        from intelligence_core.graph import store
        monkeypatch.setattr(store, "GRAPH_DIR", None)
        from intelligence_core import paths
        assert store._dir() == paths.graph_dir()


# ── evaluation/report.py ──────────────────────────────────────────────────────

class TestEvalReport:
    def test_eval_dir_sentinel_delegates_to_paths(self, monkeypatch):
        _set_project(monkeypatch, "testproject")
        import intelligence_core.evaluation.report as rep
        monkeypatch.setattr(rep, "EVAL_DIR", None)
        from intelligence_core import paths
        assert rep._eval_dir() == paths.eval_dir()

    def test_save_report_uses_override(self, monkeypatch, tmp_path):
        import intelligence_core.evaluation.report as rep
        monkeypatch.setattr(rep, "EVAL_DIR", tmp_path)
        rep.save_report(
            {"scores": {}, "targets": {}, "passed": {}, "overall_pass": True},
            "code",
        )
        files = list(tmp_path.iterdir())
        assert any("code" in f.name for f in files)


# ── evaluation/paths.py ───────────────────────────────────────────────────────

class TestEvalPaths:
    def test_get_collection_default(self, monkeypatch):
        _set_project(monkeypatch, "default")
        from intelligence_core.evaluation import paths as ep
        assert ep.get_collection("code")   == "code_intelligence"
        assert ep.get_collection("mentor") == "mentor_intelligence"

    def test_get_collection_project_prefixed(self, monkeypatch):
        _set_project(monkeypatch, "corp")
        from intelligence_core.evaluation import paths as ep
        assert ep.get_collection("code") == "corp_code_intelligence"

    def test_get_all_collections_default(self, monkeypatch):
        _set_project(monkeypatch, "default")
        from intelligence_core.evaluation import paths as ep
        assert ep.get_all_collections() == [
            "code_intelligence",
            "doc_intelligence",
            "mentor_intelligence",
        ]

    def test_get_all_collections_project(self, monkeypatch):
        _set_project(monkeypatch, "corp")
        from intelligence_core.evaluation import paths as ep
        assert ep.get_all_collections() == [
            "corp_code_intelligence",
            "corp_doc_intelligence",
            "corp_mentor_intelligence",
        ]


# ── config.py ─────────────────────────────────────────────────────────────────

class TestConfig:
    def test_is_project_default_value(self):
        from intelligence_core.config import settings
        assert settings.is_project == "default"
