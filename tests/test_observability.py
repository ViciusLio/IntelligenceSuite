"""Test suite for intelligence_core/observability.py — structured logging + metrics (v0.9.2).

Covers:
  - JSON formatter produces valid JSON with the expected fields; text format does not.
  - get_logger / configure_logging honor IS_LOG_LEVEL and attach the right handler.
  - MetricsCollector updates counters correctly and serializes all of them.
  - Thread safety of the collector under concurrent writers.
  - Question/answer text NEVER reaches the log (only metadata).
  - GET /metrics → 200 JSON when IS_METRICS_ENABLED=true, 404 by default.
"""

from __future__ import annotations

import io
import json
import logging
import threading

import pytest

from intelligence_core import observability as obs

# ─────────────────────────────────────────────────────────────────────────────
# 1. Formatters
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatters:

    def _record(self, fields: dict | None = None) -> logging.LogRecord:
        rec = logging.LogRecord("t", logging.INFO, __file__, 1, "query", None, None)
        if fields is not None:
            rec.event_fields = fields
        return rec

    def test_json_formatter_is_valid_json_with_fields(self):
        rec = self._record({"event": "query", "module": "code", "confidence": 0.91})
        out = obs.JsonFormatter().format(rec)
        data = json.loads(out)  # must not raise
        assert data["event"] == "query"
        assert data["module"] == "code"
        assert data["confidence"] == 0.91
        assert data["level"] == "INFO"
        assert data["msg"] == "query"
        assert "ts" in data

    def test_json_formatter_survives_non_serializable(self):
        from pathlib import Path
        rec = self._record({"path": Path("/tmp/x"), "obj": object()})
        # default=str must prevent a crash and still yield valid JSON
        json.loads(obs.JsonFormatter().format(rec))

    def test_text_formatter_is_not_json(self):
        rec = self._record({"event": "query"})
        out = obs.TextFormatter().format(rec)
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)
        assert "event=query" in out


# ─────────────────────────────────────────────────────────────────────────────
# 2. Logger configuration
# ─────────────────────────────────────────────────────────────────────────────

class TestLoggerConfig:

    def test_configure_json_level_and_handler(self):
        logger = obs.configure_logging(level="DEBUG", fmt="json")
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0].formatter, obs.JsonFormatter)
        assert logger.propagate is False

    def test_configure_text_handler(self):
        logger = obs.configure_logging(level="INFO", fmt="text")
        assert isinstance(logger.handlers[0].formatter, obs.TextFormatter)

    def test_invalid_level_falls_back_to_info(self):
        logger = obs.configure_logging(level="NONSENSE", fmt="json")
        assert logger.level == logging.INFO

    def test_get_logger_respects_settings_level(self, monkeypatch):
        from intelligence_core.config import settings
        monkeypatch.setattr(settings, "is_log_level", "WARNING")
        monkeypatch.setattr(settings, "is_log_format", "json")
        obs._configured = False
        logger = obs.get_logger()
        assert logger.level == logging.WARNING


# ─────────────────────────────────────────────────────────────────────────────
# 3. Metrics collector
# ─────────────────────────────────────────────────────────────────────────────

class TestCollector:

    def test_record_and_snapshot(self):
        c = obs.MetricsCollector()
        c.record_query(latency_ms=100, confidence=0.8, escalated=False)
        c.record_query(latency_ms=200, confidence=0.6, escalated=True)
        snap = c.snapshot()
        assert snap["queries_total"] == 2
        assert snap["queries_escalated"] == 1
        assert snap["avg_latency_ms"] == 150.0
        assert snap["avg_confidence"] == 0.7
        assert "uptime_seconds" in snap
        json.dumps(snap)  # every counter is JSON-serializable

    def test_empty_snapshot_no_division_by_zero(self):
        c = obs.MetricsCollector()
        snap = c.snapshot()
        assert snap["queries_total"] == 0
        assert snap["avg_latency_ms"] == 0.0
        assert snap["avg_confidence"] == 0.0

    def test_reset(self):
        c = obs.MetricsCollector()
        c.record_query(latency_ms=10, confidence=0.5, escalated=False)
        c.reset()
        assert c.snapshot()["queries_total"] == 0

    def test_thread_safety(self):
        c = obs.MetricsCollector()

        def worker():
            for _ in range(1000):
                c.record_query(latency_ms=1, confidence=0.5, escalated=True)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snap = c.snapshot()
        assert snap["queries_total"] == 8000
        assert snap["queries_escalated"] == 8000


# ─────────────────────────────────────────────────────────────────────────────
# 4. Privacy — no question/answer text in the log
# ─────────────────────────────────────────────────────────────────────────────

class TestNoTextLeak:

    def test_query_event_logs_only_metadata(self):
        obs.configure_logging(level="INFO", fmt="json")
        logger = logging.getLogger("intelligence_suite")
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(obs.JsonFormatter())
        logger.addHandler(handler)
        try:
            secret = "WHAT_IS_THE_SECRET_PASSWORD_12345"
            obs.log_query_event(
                module="code", project="default", intent="rag",
                question_length=len(secret), top_k=5, confidence=0.9,
                escalated=False, backend="ollama", latency_ms=12.3,
            )
        finally:
            logger.removeHandler(handler)

        out = buf.getvalue()
        assert secret not in out          # the text must never appear
        data = json.loads(out.strip().splitlines()[-1])
        assert data["question_length"] == len(secret)   # only the length
        assert data["event"] == "query"
        assert data["module"] == "code"

    def test_log_query_event_never_raises(self):
        # Even with hostile inputs (a mock-like object as project) it must not raise.
        class _Weird:
            def __str__(self):
                raise RuntimeError("boom")

        obs.log_query_event(
            module="code", project=_Weird(), intent="rag", question_length=3,
            top_k=5, confidence=0.5, escalated=False, backend="x", latency_ms=1.0,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Opt-in /metrics endpoint
# ─────────────────────────────────────────────────────────────────────────────

def _build_rag_app():
    from unittest.mock import MagicMock

    from intelligence_core.server_base import create_app

    mock_retriever = MagicMock()
    mock_retriever.store.count.return_value = 0
    mock_retriever.search.return_value = []
    mock_llm = MagicMock()
    mock_llm.backend_name = "mock"
    return create_app(
        title="obs test", retriever=mock_retriever, module="code",
        llm_provider=mock_llm,
    )


class TestMetricsEndpoint:

    def test_metrics_404_when_disabled(self, monkeypatch):
        from intelligence_core.config import settings
        monkeypatch.setattr(settings, "is_metrics_enabled", False)
        from fastapi.testclient import TestClient
        client = TestClient(_build_rag_app())
        assert client.get("/metrics").status_code == 404

    def test_metrics_200_when_enabled(self, monkeypatch):
        from intelligence_core.config import settings
        monkeypatch.setattr(settings, "is_metrics_enabled", True)
        from fastapi.testclient import TestClient
        client = TestClient(_build_rag_app())
        resp = client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()  # valid JSON
        for key in ("queries_total", "queries_escalated", "avg_latency_ms",
                    "avg_confidence", "uptime_seconds"):
            assert key in data


# ─────────────────────────────────────────────────────────────────────────────
# 6. Config defaults
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigDefaults:

    def test_observability_defaults(self):
        from intelligence_core.config import Settings
        s = Settings()
        assert s.is_log_level == "INFO"
        assert s.is_log_format == "json"
        assert s.is_metrics_enabled is False
