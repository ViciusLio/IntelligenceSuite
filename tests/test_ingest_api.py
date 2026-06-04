"""Tests for the optional ingest HTTP routes (v0.12.0).

Offline: the heavy parse+embed (``ingestion.ingest_path`` / ``ingest_files``) is
monkeypatched to a fast fake, so these tests exercise routing, validation, the
async job hand-off, and the opt-in gate — without Ollama or a real store.
"""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from intelligence_core import ingestion
from intelligence_core.config import settings
from intelligence_core.ingest_api import add_ingest_routes


def _build_client(monkeypatch, *, enabled=True, root="", max_mb=50, module="doc"):
    monkeypatch.setattr(settings, "is_ingest_enabled", enabled)
    monkeypatch.setattr(settings, "is_ingest_root", root)
    monkeypatch.setattr(settings, "is_ingest_max_mb", max_mb)
    app = FastAPI()
    add_ingest_routes(app, module=module)
    return TestClient(app)


def _fake_stats(**over):
    base = {"module": "doc", "collection": "doc_intelligence", "total": 1,
            "new": 1, "skipped": 0, "deleted": 0, "indexed": 1, "duration_ms": 1.0}
    base.update(over)
    return base


def _poll(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/v1/ingest/status/{job_id}").json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.02)
    raise AssertionError("job did not finish")


# ── opt-in gate ─────────────────────────────────────────────────────────────--

class TestGate:
    def test_routes_absent_when_disabled(self, monkeypatch):
        client = _build_client(monkeypatch, enabled=False)
        assert client.post("/api/v1/ingest/path", json={"path": "x"}).status_code == 404
        assert client.get("/api/v1/ingest/status/abc").status_code == 404

    def test_routes_present_when_enabled(self, monkeypatch, tmp_path):
        client = _build_client(monkeypatch, root=str(tmp_path))
        # missing required body field → 422 (route exists), not 404
        assert client.post("/api/v1/ingest/path", json={}).status_code == 422


# ── path ingest ─────────────────────────────────────────────────────────────--

class TestIngestPath:
    def test_happy_path_returns_job(self, monkeypatch, tmp_path):
        (tmp_path / "f.txt").write_text("hello world content here", encoding="utf-8")
        calls = {}

        def fake_ingest_path(mod, target, *, incremental=True):
            calls["mod"] = mod
            calls["target"] = str(target)
            return _fake_stats(module=mod)

        monkeypatch.setattr(ingestion, "ingest_path", fake_ingest_path)
        client = _build_client(monkeypatch, root=str(tmp_path))

        resp = client.post("/api/v1/ingest/path",
                           json={"path": str(tmp_path / "f.txt")})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued" and body["module"] == "doc"
        done = _poll(client, body["job_id"])
        assert done["status"] == "done"
        assert done["stats"]["new"] == 1
        assert calls["mod"] == "doc"

    def test_path_outside_root_rejected(self, monkeypatch, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "secret.txt"
        outside.write_text("nope", encoding="utf-8")
        client = _build_client(monkeypatch, root=str(allowed))
        resp = client.post("/api/v1/ingest/path", json={"path": str(outside)})
        assert resp.status_code == 400

    def test_unknown_module_rejected(self, monkeypatch, tmp_path):
        (tmp_path / "f.txt").write_text("x" * 30, encoding="utf-8")
        client = _build_client(monkeypatch, root=str(tmp_path))
        resp = client.post("/api/v1/ingest/path",
                           json={"path": str(tmp_path / "f.txt"), "module": "bogus"})
        assert resp.status_code == 400

    def test_empty_root_returns_400(self, monkeypatch, tmp_path):
        # enabled but IS_INGEST_ROOT unset → path ingest unusable
        client = _build_client(monkeypatch, root="")
        resp = client.post("/api/v1/ingest/path", json={"path": str(tmp_path)})
        assert resp.status_code == 400


# ── status ──────────────────────────────────────────────────────────────────--

class TestStatus:
    def test_unknown_job_404(self, monkeypatch, tmp_path):
        client = _build_client(monkeypatch, root=str(tmp_path))
        assert client.get("/api/v1/ingest/status/does-not-exist").status_code == 404


# ── upload ──────────────────────────────────────────────────────────────────--

class TestUpload:
    def test_upload_returns_job(self, monkeypatch, tmp_path):
        seen = {}

        def fake_ingest_files(mod, files, *, root=None, **kw):
            seen["mod"] = mod
            seen["n"] = len(list(files))
            return _fake_stats(module=mod, total=seen["n"], new=seen["n"])

        monkeypatch.setattr(ingestion, "ingest_files", fake_ingest_files)
        client = _build_client(monkeypatch, root=str(tmp_path))

        resp = client.post(
            "/api/v1/ingest/upload",
            files=[("files", ("a.txt", b"hello content", "text/plain")),
                   ("files", ("b.csv", b"x,y\n1,2\n", "text/csv"))],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["files"] == 2 and body["status"] == "queued"
        done = _poll(client, body["job_id"])
        assert done["status"] == "done"
        assert seen["n"] == 2

    def test_oversize_upload_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ingestion, "ingest_files",
                            lambda *a, **k: _fake_stats())
        client = _build_client(monkeypatch, root=str(tmp_path), max_mb=0)
        resp = client.post(
            "/api/v1/ingest/upload",
            files=[("files", ("big.txt", b"x" * 1024, "text/plain"))],
        )
        assert resp.status_code == 413
