"""OpenAI-compatible gateway server for IntelligenceSuite.

Endpoints
---------
GET  /health               liveness + the modules this gateway fronts
GET  /v1/models            OpenAI model list (4 modules + auto)
POST /v1/chat/completions  OpenAI chat — proxies to a module's /api/v1/query
                           (non-streaming here; SSE streaming added in G2)

The gateway holds no retrieval logic: it translates OpenAI ↔ IntelligenceSuite
and proxies over HTTP, forwarding the caller's Authorization header upstream.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from intelligence_gateway import translate as T

logger = logging.getLogger(__name__)

UPSTREAM_TIMEOUT = 120.0


def build_app(*, client: httpx.AsyncClient | None = None) -> FastAPI:
    """Construct the gateway app.

    Args:
        client: Optional pre-built ``httpx.AsyncClient`` (tests inject one backed
                by ``httpx.MockTransport``). When omitted, a default client is
                created lazily on first use and closed at shutdown.
    """
    from intelligence_core.config import settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.http is None:
            app.state.http = httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT)
            app.state.owns_http = True
        try:
            yield
        finally:
            if app.state.owns_http and app.state.http is not None:
                await app.state.http.aclose()

    app = FastAPI(title="IntelligenceSuite Gateway", version="0.1.0", lifespan=lifespan)
    app.state.http = client
    app.state.owns_http = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _client() -> httpx.AsyncClient:
        # lifespan startup normally sets this; lazy fallback keeps the app usable
        # if it is driven without a lifespan context.
        if app.state.http is None:
            app.state.http = httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT)
            app.state.owns_http = True
        return app.state.http

    def _forward_headers(request: Request) -> dict[str, str]:
        headers: dict[str, str] = {}
        auth = request.headers.get("authorization")
        if auth:
            headers["Authorization"] = auth
        return headers

    # ── Health ────────────────────────────────────────────────────────────────
    @app.get("/health")
    def health():
        return {
            "status":  "ok",
            "service": "intelligence-gateway",
            "modules": [r.model_id for r in T.MODULES.values()] + [T.AUTO_MODEL],
        }

    # ── Models list ───────────────────────────────────────────────────────────
    @app.get("/v1/models")
    def models():
        return {"object": "list", "data": T.list_models()}

    # ── Chat completions ──────────────────────────────────────────────────────
    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content=_err("invalid JSON body"))

        try:
            route, is_body = T.openai_to_is_request(body)
        except KeyError:
            model = body.get("model")
            return JSONResponse(
                status_code=404,
                content=_err(f"model '{model}' not found", code="model_not_found"),
            )

        stream = bool(body.get("stream", False))
        base = T.upstream_base_url(route, settings)
        model = body.get("model", route.model_id)
        headers = _forward_headers(request)

        # ── Streaming: proxy upstream SSE → OpenAI chat.completion.chunk ───────
        if stream:
            return StreamingResponse(
                _stream_completion(_client(), f"{base}/api/v1/stream", is_body, headers, model),
                media_type="text/event-stream",
                headers={
                    "Cache-Control":    "no-cache",
                    "X-Accel-Buffering": "no",
                    "X-IS-Module":      route.model_id,
                },
            )

        # ── Non-streaming ─────────────────────────────────────────────────────
        url = f"{base}/api/v1/query"
        try:
            resp = await _client().post(url, json=is_body, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("upstream %s returned %s", url, exc.response.status_code)
            return JSONResponse(
                status_code=502,
                content=_err(f"upstream error {exc.response.status_code}", code="upstream_error"),
            )
        except httpx.RequestError as exc:
            logger.warning("upstream %s unreachable: %s", url, exc)
            return JSONResponse(
                status_code=502,
                content=_err(f"upstream unreachable: {exc}", code="upstream_unreachable"),
            )

        completion = T.is_response_to_openai(resp.json(), model)
        # Expose which concrete module actually answered (useful for the 'auto' model).
        return JSONResponse(content=completion, headers={"X-IS-Module": route.model_id})

    return app


async def _stream_completion(
    client: httpx.AsyncClient,
    url: str,
    is_body: dict,
    headers: dict[str, str],
    model: str,
):
    """Proxy an upstream IntelligenceSuite SSE stream as OpenAI chat chunks.

    Emits: an opening role chunk → one content chunk per upstream ``token``
    event → a terminal ``finish_reason="stop"`` chunk → the ``[DONE]`` sentinel.
    Upstream ``sources``/``meta`` events are not part of the OpenAI text stream
    and are dropped; ``error`` events are surfaced inline as text.
    """
    chat_id = T.gen_chat_id()
    created = int(time.time())

    # Opening chunk announces the assistant role (OpenAI convention).
    yield T.format_sse(T.chat_chunk(model=model, chat_id=chat_id, created=created, role="assistant"))

    try:
        async with client.stream("POST", url, json=is_body, headers=headers) as resp:
            if resp.status_code >= 400:
                yield T.format_sse(T.chat_chunk(
                    model=model, chat_id=chat_id, created=created,
                    content=f"[upstream error {resp.status_code}]",
                ))
            else:
                async for line in resp.aiter_lines():
                    event = T.parse_sse_line(line)
                    if event is None:
                        continue
                    etype = event.get("type")
                    if etype == "token":
                        chunk = T.is_sse_event_to_openai_chunk(
                            event, model=model, chat_id=chat_id, created=created
                        )
                        if chunk is not None:
                            yield T.format_sse(chunk)
                    elif etype == "error":
                        yield T.format_sse(T.chat_chunk(
                            model=model, chat_id=chat_id, created=created,
                            content=f"[error: {event.get('error', 'unknown')}]",
                        ))
                        break
                    elif etype == "done":
                        break
                    # 'sources' / 'meta' → intentionally not emitted as text
    except httpx.RequestError as exc:
        logger.warning("stream upstream %s unreachable: %s", url, exc)
        yield T.format_sse(T.chat_chunk(
            model=model, chat_id=chat_id, created=created,
            content=f"[upstream unreachable: {exc}]",
        ))
    finally:
        yield T.format_sse(T.chat_chunk(
            model=model, chat_id=chat_id, created=created, finish_reason="stop"
        ))
        yield T.format_sse("[DONE]")


def _err(message: str, *, code: str = "bad_request") -> dict:
    """OpenAI-style error envelope."""
    return {"error": {"message": message, "type": code, "code": code}}


app = build_app()


def main() -> None:  # pragma: no cover — wired fully in Fase G3
    import uvicorn

    from intelligence_core.config import settings
    port = getattr(settings, "gw_port", 8086)
    uvicorn.run(
        "intelligence_gateway.gateway_server:app",
        host=settings.api_host,
        port=port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":  # pragma: no cover
    main()
