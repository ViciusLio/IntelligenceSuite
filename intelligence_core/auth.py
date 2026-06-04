"""Optional Bearer-token authentication for all FastAPI/ASGI apps.

IS_AUTH_ENABLED=false (default): no checks, identical to v0.8.x behaviour.
IS_AUTH_ENABLED=true: every request to a non-public path requires:
    Authorization: Bearer <IS_API_KEY>

Public paths (always accessible without a token):
    /          web UI or redirect
    /health    liveness probe — must stay public for the launcher poller
    /docs*     Swagger UI
    /redoc*    ReDoc UI
    /openapi.json  schema

Implementation note: pure ASGI middleware (not BaseHTTPMiddleware) so that
SSE streaming responses are never buffered or broken.
"""

from __future__ import annotations
import logging
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_ALWAYS_PUBLIC: frozenset[str] = frozenset({"/", "/health", "/openapi.json"})
_PUBLIC_PREFIXES: tuple[str, ...] = ("/docs", "/redoc")


def _is_public(path: str) -> bool:
    if path in _ALWAYS_PUBLIC:
        return True
    return any(path.startswith(p) for p in _PUBLIC_PREFIXES)


class BearerAuthMiddleware:
    """Pure ASGI middleware: enforces Bearer token on protected paths."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from intelligence_core.config import settings

        # Use strict identity check so test mocks (truthy MagicMock) don't
        # accidentally activate auth. Only the real boolean True enables it.
        if settings.is_auth_enabled is not True:
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if _is_public(path):
            await self.app(scope, receive, send)
            return

        # Reject immediately if no key is configured (misconfiguration guard)
        if not settings.is_api_key:
            await _reject(scope, receive, send)
            return

        raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        auth_value = next(
            (v.decode() for k, v in raw_headers if k == b"authorization"), ""
        )

        if auth_value != f"Bearer {settings.is_api_key}":
            await _reject(scope, receive, send)
            return

        await self.app(scope, receive, send)


async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
    response = Response(
        content='{"detail":"Unauthorized"}',
        status_code=401,
        media_type="application/json",
    )
    await response(scope, receive, send)


def add_auth_middleware(app: ASGIApp) -> None:
    """Attach BearerAuthMiddleware to a FastAPI app.

    Call this *after* CORSMiddleware has been added, so auth is the outermost
    layer and unauthorised requests are rejected before reaching any handler.
    """
    app.add_middleware(BearerAuthMiddleware)


def warn_if_key_missing() -> None:
    """Log a startup warning when auth is enabled but IS_API_KEY is empty."""
    from intelligence_core.config import settings
    if settings.is_auth_enabled is True and not settings.is_api_key:
        logger.warning(
            "IS_AUTH_ENABLED=true but IS_API_KEY is empty — "
            "all API requests will be rejected with 401. "
            "Set IS_API_KEY in your .env file."
        )
