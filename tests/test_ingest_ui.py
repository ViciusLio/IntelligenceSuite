"""Tests for the SOTTO-FASE C ingest UI (v0.12.0).

Two concerns, both offline:
  1. ``/health`` now exposes ``ingest_enabled`` so the browser can gate the
     ingest panel — verified for the shared RAG app (Code/Doc/Mentor) and for
     the standalone ProposalIntelligence server.
  2. The HTML templates carry the ingest-panel markers (button, modal, JS
     hooks) used by that gate.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient


# ── /health exposes ingest_enabled ──────────────────────────────────────────--

def _build_rag_app():
    from intelligence_core.server_base import create_app

    retriever = MagicMock()
    retriever.store.count.return_value = 0
    retriever.search.return_value = []
    llm = MagicMock()
    llm.backend_name = "mock"
    return create_app(title="ui test", retriever=retriever, module="code",
                      llm_provider=llm)


class TestHealthIngestFlag:
    def test_rag_health_reports_disabled_by_default(self, monkeypatch):
        from intelligence_core.config import settings
        monkeypatch.setattr(settings, "is_ingest_enabled", False)
        body = TestClient(_build_rag_app()).get("/health").json()
        assert body["ingest_enabled"] is False

    def test_rag_health_reports_enabled(self, monkeypatch):
        from intelligence_core.config import settings
        monkeypatch.setattr(settings, "is_ingest_enabled", True)
        body = TestClient(_build_rag_app()).get("/health").json()
        assert body["ingest_enabled"] is True

    def test_proposal_health_reports_ingest_flag(self, monkeypatch):
        from intelligence_core.config import settings
        monkeypatch.setattr(settings, "is_ingest_enabled", True)
        from ProposalIntelligence import proposal_server
        client = TestClient(proposal_server.build_app())
        body = client.get("/health").json()
        assert body["ingest_enabled"] is True


# ── templates carry the ingest-panel markers ────────────────────────────────--

class TestTemplateMarkers:
    def test_chat_html_has_ingest_panel(self):
        from intelligence_ui.templates import CHAT_HTML
        for marker in ("ingest-btn", "ingest-modal", "openIngest",
                       "submitIngest", "pollIngest",
                       "/api/v1/ingest/upload", "/api/v1/ingest/path",
                       "/api/v1/ingest/status/"):
            assert marker in CHAT_HTML, marker

    def test_chat_html_has_export_control(self):
        from intelligence_ui.templates import CHAT_HTML
        for marker in ("export-btn", "downloadExport", "/api/v1/export"):
            assert marker in CHAT_HTML, marker

    def test_proposal_html_has_ingest_panel(self):
        from ProposalIntelligence.web import PROPOSAL_HTML
        for marker in ("ingest-btn", "ingest-modal", "openIngest",
                       "submitIngest", "pollIngest",
                       "/api/v1/ingest/upload", "/api/v1/ingest/status/"):
            assert marker in PROPOSAL_HTML, marker

    def test_proposal_html_has_export_control(self):
        from ProposalIntelligence.web import PROPOSAL_HTML
        for marker in ("export-btn", "downloadExport", "/api/v1/export"):
            assert marker in PROPOSAL_HTML, marker
