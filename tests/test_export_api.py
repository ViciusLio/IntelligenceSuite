"""Tests for the export renderers and HTTP route (SOTTO-FASE D).

Offline: Markdown/HTML are stdlib; PDF uses ``fpdf2`` when present. The
dependency-missing path is exercised by monkeypatching the ``_HAS_FPDF`` flag,
so the 503 branch is covered regardless of whether fpdf2 is installed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from intelligence_core import export

SECTIONS = [
    {"heading": "Domanda 1", "body": "Avete esperienza cloud?",
     "sources": [{"source": "qa/cloud.md", "score": 0.9}]},
    {"heading": "Risposta", "body": "Sì — molti progetti.", "sources": []},
]


# ── renderers ────────────────────────────────────────────────────────────────

class TestRenderers:
    def test_markdown_contains_title_and_sections(self):
        md = export.render_markdown("Report", SECTIONS)
        assert md.startswith("# Report")
        assert "## Domanda 1" in md
        assert "Avete esperienza cloud?" in md
        assert "_Fonti: qa/cloud.md_" in md

    def test_html_is_escaped_standalone_doc(self):
        html = export.render_html("R&D <b>", [{"heading": "<x>", "body": "a & b"}])
        assert html.startswith("<!DOCTYPE html>")
        assert "R&amp;D &lt;b&gt;" in html       # title escaped
        assert "&lt;x&gt;" in html               # heading escaped
        assert "a &amp; b" in html               # body escaped

    def test_markdown_handles_empty(self):
        assert export.render_markdown(None, []).strip() == ""


# ── PDF (skips cleanly if fpdf2 absent) ──────────────────────────────────────

class TestPdf:
    def test_pdf_bytes_when_available(self):
        if not export._HAS_FPDF:
            pytest.skip("fpdf2 not installed")
        data = export.render_pdf("Report — éàù “ok”", SECTIONS)
        assert isinstance(data, (bytes, bytearray))
        assert bytes(data).startswith(b"%PDF")

    def test_pdf_raises_when_missing(self, monkeypatch):
        monkeypatch.setattr(export, "_HAS_FPDF", False)
        with pytest.raises(export.ExportDependencyError):
            export.render_pdf("x", SECTIONS)


# ── HTTP route ───────────────────────────────────────────────────────────────

def _build_app():
    from intelligence_core.server_base import create_app

    retriever = MagicMock()
    retriever.store.count.return_value = 0
    retriever.search.return_value = []
    llm = MagicMock()
    llm.backend_name = "mock"
    return create_app(title="export test", retriever=retriever, module="doc",
                      llm_provider=llm)


class TestExportRoute:
    def setup_method(self):
        self.client = TestClient(_build_app())

    def _post(self, fmt):
        return self.client.post("/api/v1/export",
                                json={"format": fmt, "title": "Conversazione",
                                      "sections": SECTIONS})

    def test_markdown_download(self):
        r = self._post("markdown")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        assert "attachment" in r.headers["content-disposition"]
        assert "conversazione.md" in r.headers["content-disposition"]
        assert "# Conversazione" in r.text

    def test_html_download(self):
        r = self._post("html")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert r.text.startswith("<!DOCTYPE html>")

    def test_unknown_format_400(self):
        assert self._post("docx").status_code == 400

    def test_pdf_503_when_dependency_missing(self, monkeypatch):
        monkeypatch.setattr(export, "_HAS_FPDF", False)
        assert self._post("pdf").status_code == 503

    def test_pdf_download_when_available(self):
        if not export._HAS_FPDF:
            pytest.skip("fpdf2 not installed")
        r = self._post("pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF")
