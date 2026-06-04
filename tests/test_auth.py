"""Tests for IS_AUTH_ENABLED / IS_API_KEY Bearer-token authentication (FASE 2 — v0.9.1)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_client(monkeypatch, *, auth_enabled: bool, api_key: str) -> TestClient:
    """Minimal FastAPI app + BearerAuthMiddleware for isolated middleware testing."""
    from intelligence_core.config import settings
    monkeypatch.setattr(settings, "is_auth_enabled", auth_enabled)
    monkeypatch.setattr(settings, "is_api_key", api_key)

    from intelligence_core.auth import add_auth_middleware

    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def root():
        return JSONResponse({"page": "ui"})

    @app.get("/docs", include_in_schema=False)
    def docs():
        return JSONResponse({"page": "docs"})

    @app.get("/api/v1/data")
    def data():
        return {"secret": "value"}

    @app.post("/api/v1/query")
    def query():
        return {"answer": "42"}

    add_auth_middleware(app)
    return TestClient(app, raise_server_exceptions=False)


# ── auth disabled (default) ───────────────────────────────────────────────────

class TestAuthDisabled:
    def test_api_endpoint_no_header_passes(self, monkeypatch):
        c = _build_client(monkeypatch, auth_enabled=False, api_key="")
        assert c.get("/api/v1/data").status_code == 200

    def test_api_post_no_header_passes(self, monkeypatch):
        c = _build_client(monkeypatch, auth_enabled=False, api_key="")
        assert c.post("/api/v1/query").status_code == 200

    def test_health_passes(self, monkeypatch):
        c = _build_client(monkeypatch, auth_enabled=False, api_key="")
        assert c.get("/health").status_code == 200


# ── auth enabled, correct key ─────────────────────────────────────────────────

class TestAuthEnabledCorrectKey:
    def test_correct_bearer_passes(self, monkeypatch):
        c = _build_client(monkeypatch, auth_enabled=True, api_key="s3cr3t")
        resp = c.get("/api/v1/data", headers={"Authorization": "Bearer s3cr3t"})
        assert resp.status_code == 200

    def test_correct_bearer_on_post(self, monkeypatch):
        c = _build_client(monkeypatch, auth_enabled=True, api_key="s3cr3t")
        resp = c.post("/api/v1/query", headers={"Authorization": "Bearer s3cr3t"})
        assert resp.status_code == 200

    def test_health_always_public(self, monkeypatch):
        c = _build_client(monkeypatch, auth_enabled=True, api_key="s3cr3t")
        assert c.get("/health").status_code == 200

    def test_root_always_public(self, monkeypatch):
        c = _build_client(monkeypatch, auth_enabled=True, api_key="s3cr3t")
        assert c.get("/").status_code == 200

    def test_docs_always_public(self, monkeypatch):
        c = _build_client(monkeypatch, auth_enabled=True, api_key="s3cr3t")
        assert c.get("/docs").status_code == 200


# ── auth enabled, wrong / missing key ────────────────────────────────────────

class TestAuthEnabledRejections:
    def test_missing_header_returns_401(self, monkeypatch):
        c = _build_client(monkeypatch, auth_enabled=True, api_key="s3cr3t")
        assert c.get("/api/v1/data").status_code == 401

    def test_wrong_token_returns_401(self, monkeypatch):
        c = _build_client(monkeypatch, auth_enabled=True, api_key="s3cr3t")
        resp = c.get("/api/v1/data", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_bare_key_without_bearer_prefix_returns_401(self, monkeypatch):
        c = _build_client(monkeypatch, auth_enabled=True, api_key="s3cr3t")
        resp = c.get("/api/v1/data", headers={"Authorization": "s3cr3t"})
        assert resp.status_code == 401

    def test_401_json_body(self, monkeypatch):
        c = _build_client(monkeypatch, auth_enabled=True, api_key="s3cr3t")
        resp = c.get("/api/v1/data")
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized"}

    def test_empty_api_key_rejects_everything(self, monkeypatch):
        c = _build_client(monkeypatch, auth_enabled=True, api_key="")
        resp = c.get("/api/v1/data", headers={"Authorization": "Bearer "})
        assert resp.status_code == 401

    def test_empty_api_key_even_with_empty_bearer(self, monkeypatch):
        c = _build_client(monkeypatch, auth_enabled=True, api_key="")
        assert c.get("/api/v1/data").status_code == 401


# ── warn_if_key_missing ───────────────────────────────────────────────────────

class TestWarnIfKeyMissing:
    def test_no_warning_when_auth_disabled(self, monkeypatch, caplog):
        from intelligence_core.config import settings
        monkeypatch.setattr(settings, "is_auth_enabled", False)
        monkeypatch.setattr(settings, "is_api_key", "")
        from intelligence_core.auth import warn_if_key_missing
        import logging
        with caplog.at_level(logging.WARNING, logger="intelligence_core.auth"):
            warn_if_key_missing()
        assert "IS_API_KEY" not in caplog.text

    def test_warning_emitted_when_auth_enabled_no_key(self, monkeypatch, caplog):
        from intelligence_core.config import settings
        monkeypatch.setattr(settings, "is_auth_enabled", True)
        monkeypatch.setattr(settings, "is_api_key", "")
        from intelligence_core.auth import warn_if_key_missing
        import logging
        with caplog.at_level(logging.WARNING, logger="intelligence_core.auth"):
            warn_if_key_missing()
        assert "IS_API_KEY" in caplog.text

    def test_no_warning_when_key_is_set(self, monkeypatch, caplog):
        from intelligence_core.config import settings
        monkeypatch.setattr(settings, "is_auth_enabled", True)
        monkeypatch.setattr(settings, "is_api_key", "somekey")
        from intelligence_core.auth import warn_if_key_missing
        import logging
        with caplog.at_level(logging.WARNING, logger="intelligence_core.auth"):
            warn_if_key_missing()
        assert "IS_API_KEY" not in caplog.text


# ── config defaults ───────────────────────────────────────────────────────────

class TestConfigDefaults:
    def test_is_auth_enabled_default_false(self):
        from intelligence_core.config import settings
        assert settings.is_auth_enabled is False

    def test_is_api_key_default_empty(self):
        from intelligence_core.config import settings
        assert settings.is_api_key == ""
