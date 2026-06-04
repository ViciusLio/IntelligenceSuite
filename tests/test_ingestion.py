"""Tests for the on-demand ingestion service (v0.11.0).

Fully offline: a tiny deterministic ``FakeEmbedder`` and a tmp-dir ChromaStore
(no Ollama, no network). Verifies parsing dispatch, in-store idempotency,
IS_INGEST_ROOT path safety, and the async job registry.
"""

from __future__ import annotations

import time

import pytest

from intelligence_core import ingestion
from intelligence_core.config import settings


class FakeEmbedder:
    """Deterministic 8-dim embedder: stable per text, non-zero (store keeps it)."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            h = abs(hash(t)) % 997 + 1
            out.append([float((h >> i) & 1) + 0.1 for i in range(8)])
        return out

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()


@pytest.fixture
def persist_dir(tmp_path):
    return str(tmp_path / "chroma")


# ── csv parser ────────────────────────────────────────────────────────────────

class TestCsvParser:
    def test_can_parse(self, tmp_path):
        from DocIntelligence.parsers import csv_parser
        assert csv_parser.can_parse(tmp_path / "x.csv")
        assert csv_parser.can_parse(tmp_path / "x.tsv")
        assert not csv_parser.can_parse(tmp_path / "x.txt")

    def test_registry_picks_csv(self, tmp_path):
        from DocIntelligence.parsers import get_parser
        f = tmp_path / "data.csv"
        f.write_text("a,b\n1,2\n", encoding="utf-8")
        parser = get_parser(f)
        assert parser is not None
        assert parser.can_parse(f)

    def test_parse_produces_section_and_table(self, tmp_path):
        from DocIntelligence.parsers import csv_parser
        f = tmp_path / "people.csv"
        f.write_text("name,role\nAda,eng\nGrace,admiral\n", encoding="utf-8")
        chunks = csv_parser.parse_file(f, tmp_path)
        types = {c["type"] for c in chunks}
        assert "section" in types and "table" in types
        assert all(c["domain"] == "doc" for c in chunks)
        table = next(c for c in chunks if c["type"] == "table")
        assert "Ada" in table["text"] and "role" in table["text"]

    def test_empty_csv_is_safe(self, tmp_path):
        from DocIntelligence.parsers import csv_parser
        f = tmp_path / "empty.csv"
        f.write_text("", encoding="utf-8")
        chunks = csv_parser.parse_file(f, tmp_path)
        assert len(chunks) == 1  # raw fallback, no crash


# ── ingest_files (upload mode) ──────────────────────────────────────────────--

class TestIngestFilesDoc:
    def _mkdocs(self, tmp_path):
        (tmp_path / "a.txt").write_text(
            "Questo e' un paragrafo abbastanza lungo da diventare un chunk doc valido "
            "con parecchie parole utili al test.", encoding="utf-8")
        (tmp_path / "b.csv").write_text("col1,col2\nval1,val2\n", encoding="utf-8")
        return [tmp_path / "a.txt", tmp_path / "b.csv"]

    def test_ingests_and_indexes(self, tmp_path, persist_dir, fake_embedder):
        files = self._mkdocs(tmp_path)
        stats = ingestion.ingest_files(
            "doc", files, root=tmp_path,
            persist_dir=persist_dir, embedder=fake_embedder,
        )
        assert stats["total"] > 0
        assert stats["new"] == stats["total"]
        assert stats["indexed"] == stats["total"]
        assert stats["deleted"] == 0  # upload mode never prunes

    def test_idempotent_second_run(self, tmp_path, persist_dir, fake_embedder):
        files = self._mkdocs(tmp_path)
        first = ingestion.ingest_files(
            "doc", files, root=tmp_path,
            persist_dir=persist_dir, embedder=fake_embedder)
        second = ingestion.ingest_files(
            "doc", files, root=tmp_path,
            persist_dir=persist_dir, embedder=fake_embedder)
        assert second["new"] == 0
        assert second["skipped"] == second["total"] == first["total"]
        assert second["indexed"] == first["indexed"]


class TestIngestFilesOtherModules:
    def test_mentor_practice(self, tmp_path, persist_dir, fake_embedder):
        f = tmp_path / "guida.md"
        f.write_text(
            "# Onboarding\n\n## Setup\nInstalla gli strumenti e configura "
            "l'ambiente di sviluppo locale come descritto.\n", encoding="utf-8")
        stats = ingestion.ingest_files(
            "mentor", [f], root=tmp_path,
            persist_dir=persist_dir, embedder=fake_embedder)
        assert stats["total"] > 0 and stats["new"] == stats["total"]

    def test_proposal_qa(self, tmp_path, persist_dir, fake_embedder):
        f = tmp_path / "qa.md"
        f.write_text(
            "D: Qual e' la durata della garanzia?\n"
            "R: La garanzia ha durata di 24 mesi.\n\n"
            "D: Supportate il single sign-on?\n"
            "R: Si, supportiamo SSO via SAML e OIDC.\n", encoding="utf-8")
        stats = ingestion.ingest_files(
            "proposal", [f], root=tmp_path,
            persist_dir=persist_dir, embedder=fake_embedder)
        assert stats["total"] == 2 and stats["new"] == 2


# ── module validation ───────────────────────────────────────────────────────--

class TestModuleValidation:
    def test_unknown_module_raises(self, tmp_path, persist_dir, fake_embedder):
        with pytest.raises(ingestion.UnknownModuleError):
            ingestion.ingest_files(
                "bogus", [], root=tmp_path,
                persist_dir=persist_dir, embedder=fake_embedder)


# ── path safety (IS_INGEST_ROOT) ────────────────────────────────────────────--

class TestPathValidation:
    def test_disabled_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "is_ingest_enabled", False)
        with pytest.raises(ingestion.IngestionDisabledError):
            ingestion.validate_path(tmp_path)

    def test_empty_root_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "is_ingest_enabled", True)
        monkeypatch.setattr(settings, "is_ingest_root", "")
        with pytest.raises(ingestion.IngestionRootError):
            ingestion.validate_path(tmp_path)

    def test_outside_root_raises(self, tmp_path, monkeypatch):
        root = tmp_path / "allowed"
        root.mkdir()
        outside = tmp_path / "secret"
        outside.mkdir()
        monkeypatch.setattr(settings, "is_ingest_enabled", True)
        monkeypatch.setattr(settings, "is_ingest_root", str(root))
        with pytest.raises(ingestion.IngestionRootError):
            ingestion.validate_path(outside)

    def test_inside_root_ok(self, tmp_path, monkeypatch):
        root = tmp_path / "allowed"
        (root / "sub").mkdir(parents=True)
        monkeypatch.setattr(settings, "is_ingest_enabled", True)
        monkeypatch.setattr(settings, "is_ingest_root", str(root))
        resolved = ingestion.validate_path(root / "sub")
        assert resolved == (root / "sub").resolve()


class TestIngestPath:
    def test_full_scan_prunes_orphans(self, tmp_path, persist_dir, fake_embedder, monkeypatch):
        root = tmp_path / "docs"
        root.mkdir()
        (root / "keep.txt").write_text(
            "Paragrafo iniziale sufficientemente lungo per generare un chunk "
            "di documentazione valido nel test.", encoding="utf-8")
        gone = root / "gone.txt"
        gone.write_text(
            "Secondo paragrafo altrettanto lungo destinato a sparire al "
            "secondo passaggio incrementale di prova.", encoding="utf-8")
        monkeypatch.setattr(settings, "is_ingest_enabled", True)
        monkeypatch.setattr(settings, "is_ingest_root", str(root))

        first = ingestion.ingest_path(
            "doc", root, persist_dir=persist_dir, embedder=fake_embedder)
        assert first["new"] == first["total"] > 0

        gone.unlink()
        second = ingestion.ingest_path(
            "doc", root, persist_dir=persist_dir, embedder=fake_embedder)
        assert second["deleted"] >= 1
        assert second["indexed"] < first["indexed"]


# ── async job registry ──────────────────────────────────────────────────────--

class TestJobRegistry:
    def test_submit_completes(self):
        reg = ingestion.JobRegistry()
        job_id = ingestion.submit("doc", lambda: {"ok": True}, registry=reg)
        _wait(reg, job_id)
        job = reg.get(job_id)
        assert job.status == "done"
        assert job.stats == {"ok": True}
        assert job.error is None

    def test_submit_captures_error(self):
        reg = ingestion.JobRegistry()

        def boom():
            raise ValueError("kaboom")

        job_id = ingestion.submit("doc", boom, registry=reg)
        _wait(reg, job_id)
        job = reg.get(job_id)
        assert job.status == "error"
        assert "kaboom" in job.error

    def test_unknown_module_rejected_before_thread(self):
        with pytest.raises(ingestion.UnknownModuleError):
            ingestion.submit("nope", lambda: {})

    def test_to_dict_shape(self):
        reg = ingestion.JobRegistry()
        job = reg.create("doc")
        d = job.to_dict()
        assert set(d) >= {"job_id", "module", "status", "created_at", "stats", "error"}


def _wait(registry, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = registry.get(job_id)
        if job and job.status in ("done", "error"):
            return
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")
