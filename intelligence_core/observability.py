"""Structured observability for the Intelligence Suite — logging + in-memory metrics.

Two independent, dependency-free capabilities (stdlib only):

1. **Structured logging** — a centralized logger that emits one JSON object per
   line to stdout by default (``IS_LOG_FORMAT=json``), with a human-readable text
   fallback for local development (``IS_LOG_FORMAT=text``). Level via
   ``IS_LOG_LEVEL`` (default ``INFO``).

   Structured events carry **only metadata** — never the text of a question or an
   answer. Question/answer bodies are potentially sensitive and must never reach
   the logs; we log the question *length*, not its content.

2. **In-memory metrics** — a per-process, thread-safe counter container exposed
   (opt-in) at ``GET /metrics`` when ``IS_METRICS_ENABLED=true``. Counters reset
   on restart. No external dependency: a plain object guarded by a lock.

Everything here is best-effort: an observability failure must never break a
request or an ingestion run. Public helpers swallow their own exceptions.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from datetime import datetime, timezone

# Standard LogRecord attributes — anything not in here that we attach via
# ``extra=`` is treated as a structured field.
_BASE_LOGGER_NAME = "intelligence_suite"


# ─────────────────────────────────────────────────────────────────────────────
# Formatters
# ─────────────────────────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """Render each record as a single-line JSON object.

    Structured fields are passed through ``logger.info(msg, extra={"event_fields":
    {...}})`` and merged into the top-level object. ``default=str`` guarantees we
    never crash on a non-serializable value (e.g. a Path or a mock).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        fields = getattr(record, "event_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable single line: ``<time> <LEVEL> <logger> — <msg> | k=v k=v``."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        fields = getattr(record, "event_fields", None)
        if isinstance(fields, dict) and fields:
            extra = " ".join(f"{k}={v}" for k, v in fields.items())
            return f"{base} | {extra}"
        return base


def _make_handler(fmt: str) -> logging.Handler:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter() if str(fmt).lower() != "text" else TextFormatter())
    return handler


# ─────────────────────────────────────────────────────────────────────────────
# Logger configuration
# ─────────────────────────────────────────────────────────────────────────────

_logger_lock = threading.Lock()
_configured = False


def configure_logging(
    level: str | int | None = None,
    fmt: str | None = None,
    name: str = _BASE_LOGGER_NAME,
) -> logging.Logger:
    """(Re)configure and return the centralized suite logger.

    Reads ``IS_LOG_LEVEL`` / ``IS_LOG_FORMAT`` from settings when ``level`` /
    ``fmt`` are not given. Idempotent in spirit: replaces existing handlers so a
    second call with new parameters simply re-points the logger. ``propagate`` is
    disabled so structured events are not duplicated through the root logger.
    """
    if level is None or fmt is None:
        try:
            from intelligence_core.config import settings
            if level is None:
                level = getattr(settings, "is_log_level", "INFO")
            if fmt is None:
                fmt = getattr(settings, "is_log_format", "json")
        except Exception:
            level = level or "INFO"
            fmt = fmt or "json"

    logger = logging.getLogger(name)
    with _logger_lock:
        for h in list(logger.handlers):
            logger.removeHandler(h)
        logger.addHandler(_make_handler(fmt))
        # Resolve level: accept int, level name, or fall back to INFO on garbage.
        resolved = logging.INFO
        if isinstance(level, int):
            resolved = level
        elif isinstance(level, str):
            resolved = logging.getLevelName(level.upper())
            if not isinstance(resolved, int):
                resolved = logging.INFO
        logger.setLevel(resolved)
        logger.propagate = False
        global _configured
        _configured = True
    return logger


def get_logger(name: str = _BASE_LOGGER_NAME) -> logging.Logger:
    """Return the suite logger, configuring it once from settings on first use."""
    logger = logging.getLogger(name)
    if not _configured or not logger.handlers:
        return configure_logging(name=name)
    return logger


# ─────────────────────────────────────────────────────────────────────────────
# In-memory metrics collector (per-process, thread-safe)
# ─────────────────────────────────────────────────────────────────────────────

class MetricsCollector:
    """Thread-safe in-memory counters. Reset on process restart."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._queries_total = 0
            self._queries_escalated = 0
            self._sum_latency_ms = 0.0
            self._sum_confidence = 0.0
            self._started_at = time.time()

    def record_query(
        self,
        *,
        latency_ms: float,
        confidence: float,
        escalated: bool,
    ) -> None:
        """Record one query. Coerces values defensively; never raises."""
        with self._lock:
            self._queries_total += 1
            if escalated:
                self._queries_escalated += 1
            try:
                self._sum_latency_ms += float(latency_ms)
            except (TypeError, ValueError):
                pass
            try:
                self._sum_confidence += float(confidence)
            except (TypeError, ValueError):
                pass

    def snapshot(self) -> dict:
        """Serialize all counters into a plain JSON-ready dict."""
        with self._lock:
            total = self._queries_total
            avg_latency = (self._sum_latency_ms / total) if total else 0.0
            avg_confidence = (self._sum_confidence / total) if total else 0.0
            return {
                "queries_total": total,
                "queries_escalated": self._queries_escalated,
                "avg_latency_ms": round(avg_latency, 2),
                "avg_confidence": round(avg_confidence, 4),
                "uptime_seconds": round(time.time() - self._started_at, 1),
            }


# Module-level singleton: shared by every server in the same process.
metrics = MetricsCollector()


# ─────────────────────────────────────────────────────────────────────────────
# Event emitters (best-effort — never raise)
# ─────────────────────────────────────────────────────────────────────────────

def log_query_event(
    *,
    module: str,
    project: str,
    intent: str,
    question_length: int,
    top_k: int,
    confidence: float,
    escalated: bool,
    backend: str,
    latency_ms: float,
) -> None:
    """Emit one structured ``query`` event and update the metrics counters.

    NEVER receives or logs the question/answer text — only ``question_length``.
    Wrapped so an observability failure cannot break the response path.
    """
    try:
        get_logger().info(
            "query",
            extra={
                "event_fields": {
                    "event": "query",
                    "module": module,
                    "project": project,
                    "intent": intent,
                    "question_length": question_length,
                    "top_k": top_k,
                    "confidence": confidence,
                    "escalated": escalated,
                    "backend": backend,
                    "latency_ms": latency_ms,
                }
            },
        )
    except Exception:
        pass
    try:
        metrics.record_query(
            latency_ms=latency_ms, confidence=confidence, escalated=escalated
        )
    except Exception:
        pass


def log_ingestion_event(
    *,
    module: str,
    project: str,
    total: int,
    new: int,
    skipped: int,
    duration_ms: float,
    backend: str,
) -> None:
    """Emit one structured ``ingestion`` event at the end of an embed run."""
    try:
        get_logger().info(
            "ingestion",
            extra={
                "event_fields": {
                    "event": "ingestion",
                    "module": module,
                    "project": project,
                    "chunks_total": total,
                    "chunks_new": new,
                    "chunks_skipped": skipped,
                    "duration_ms": round(duration_ms, 1),
                    "backend": backend,
                }
            },
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Opt-in /metrics endpoint
# ─────────────────────────────────────────────────────────────────────────────

def add_metrics_endpoint(app) -> None:
    """Register ``GET /metrics`` only when ``IS_METRICS_ENABLED`` is exactly True.

    When disabled the route is never registered, so the path returns 404 — the
    contract required by the spec. Strict identity check (``is True``) mirrors the
    auth middleware: test suites that patch ``settings`` with a truthy MagicMock
    must not accidentally expose the endpoint.
    """
    try:
        from intelligence_core.config import settings
        if settings.is_metrics_enabled is not True:
            return
    except Exception:
        return

    from fastapi.responses import JSONResponse

    @app.get("/metrics", include_in_schema=False)
    def _metrics():
        return JSONResponse(metrics.snapshot())
