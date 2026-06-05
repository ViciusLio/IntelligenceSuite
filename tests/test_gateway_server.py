"""Endpoint tests for intelligence_gateway.gateway_server (G1).

Upstream IntelligenceSuite servers are faked with httpx.MockTransport, so these
tests need no running server and no network. They verify:
  * GET /health and GET /v1/models
  * POST /v1/chat/completions (non-streaming) translation + routing
  * Authorization header is forwarded upstream
  * unknown model → 404, upstream failure → 502, stream=true → 501 (pre-G2)
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from intelligence_gateway.gateway_server import build_app

# Default upstream answer used by most handlers.
_QR = {
    "answer":     "risposta dal modulo",
    "sources":    [{"id": "x", "source": "f.py", "type": "function", "score": 0.91}],
    "confidence": 0.91,
    "escalated":  False,
    "backend":    "ollama",
    "latency_ms": 12.3,
    "intent":     "rag",
}


def _client_with_capture(captured: list, *, status: int = 200, json_body=None):
    """Build an httpx.AsyncClient whose MockTransport records every request."""
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status, json=json_body if json_body is not None else _QR)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _app(captured: list, **kw):
    return build_app(client=_client_with_capture(captured, **kw))


# ── Health / models ───────────────────────────────────────────────────────────

def test_health():
    captured: list = []
    with TestClient(_app(captured)) as c:
        r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "intelligence-suite" in body["modules"]


def test_models_lists_five():
    captured: list = []
    with TestClient(_app(captured)) as c:
        r = c.get("/v1/models")
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "list"
    ids = {m["id"] for m in data["data"]}
    assert ids == {
        "code-intelligence", "doc-intelligence", "mentor-intelligence",
        "proposal-intelligence", "intelligence-suite",
    }


# ── Chat completions — happy path ─────────────────────────────────────────────

def test_chat_completion_nonstreaming():
    captured: list = []
    with TestClient(_app(captured)) as c:
        r = c.post("/v1/chat/completions", json={
            "model": "code-intelligence",
            "messages": [{"role": "user", "content": "dov'è Retriever?"}],
        })
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "code-intelligence"
    assert body["choices"][0]["message"]["content"] == "risposta dal modulo"
    assert body["choices"][0]["finish_reason"] == "stop"
    # which module answered, surfaced as a header
    assert r.headers["X-IS-Module"] == "code-intelligence"

    # upstream was called once, on the right path, with the translated body
    assert len(captured) == 1
    req = captured[0]
    assert req.url.path == "/api/v1/query"
    import json as _json
    sent = _json.loads(req.content)
    assert sent["question"] == "dov'è Retriever?"
    assert sent["history"] == []


def test_chat_completion_forwards_history():
    captured: list = []
    with TestClient(_app(captured)) as c:
        c.post("/v1/chat/completions", json={
            "model": "doc-intelligence",
            "messages": [
                {"role": "user",      "content": "prima"},
                {"role": "assistant", "content": "ok"},
                {"role": "user",      "content": "seconda"},
            ],
        })
    import json as _json
    sent = _json.loads(captured[0].content)
    assert sent["question"] == "seconda"
    assert sent["history"] == [
        {"role": "user", "content": "prima"},
        {"role": "assistant", "content": "ok"},
    ]


def test_auto_model_routes_to_mentor_port():
    captured: list = []
    with TestClient(_app(captured)) as c:
        r = c.post("/v1/chat/completions", json={
            "model": "intelligence-suite",
            "messages": [{"role": "user", "content": "come inizio l'onboarding da junior?"}],
        })
    assert r.status_code == 200
    # auto-routing picked mentor → upstream hit mentor's port (mi_port=8082)
    from intelligence_core.config import settings
    assert captured[0].url.port == settings.mi_port
    assert r.headers["X-IS-Module"] == "mentor-intelligence"


def test_authorization_header_forwarded():
    captured: list = []
    with TestClient(_app(captured)) as c:
        c.post(
            "/v1/chat/completions",
            json={"model": "doc-intelligence",
                  "messages": [{"role": "user", "content": "ciao"}]},
            headers={"Authorization": "Bearer secret-123"},
        )
    assert captured[0].headers.get("authorization") == "Bearer secret-123"


# ── ProposalIntelligence as a standard module ─────────────────────────────────
# Proposal now exposes the standard /api/v1/query + /api/v1/stream contract, so
# the gateway drives it exactly like the other modules — no special-casing.

def test_proposal_nonstreaming_uses_standard_query():
    captured: list = []
    with TestClient(_app(captured, json_body={"answer": "risposta di gara", "sources": []})) as c:
        r = c.post("/v1/chat/completions", json={
            "model": "proposal-intelligence",
            "messages": [{"role": "user", "content": "Rispondi al requisito"}],
        })
    assert r.status_code == 200
    body = r.json()
    assert body["choices"][0]["message"]["content"] == "risposta di gara"
    assert r.headers["X-IS-Module"] == "proposal-intelligence"
    # standard single-question contract, on the standard path
    assert len(captured) == 1
    req = captured[0]
    assert req.url.path == "/api/v1/query"
    from intelligence_core.config import settings
    assert req.url.port == settings.pi_port
    sent = json.loads(req.content)
    assert sent["question"] == "Rispondi al requisito"


def test_proposal_streaming_uses_standard_stream_endpoint():
    captured: list = []
    with TestClient(_streaming_app(captured)) as c:
        r = c.post("/v1/chat/completions", json={
            "model": "proposal-intelligence",
            "stream": True,
            "messages": [{"role": "user", "content": "Rispondi al requisito"}],
        })
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    # real SSE proxying, same as the other modules
    assert captured[0].url.path == "/api/v1/stream"
    payloads = _data_payloads(r.text)
    assert payloads[-1] == "[DONE]"
    chunks = [json.loads(p) for p in payloads if p != "[DONE]"]
    content = "".join(ch["choices"][0]["delta"].get("content", "") for ch in chunks)
    assert content == "Ciao mondo"


# ── Error paths ───────────────────────────────────────────────────────────────

def test_unknown_model_404():
    captured: list = []
    with TestClient(_app(captured)) as c:
        r = c.post("/v1/chat/completions", json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "ciao"}],
        })
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "model_not_found"
    assert captured == []  # never reached upstream


def test_upstream_error_502():
    captured: list = []
    with TestClient(_app(captured, status=500)) as c:
        r = c.post("/v1/chat/completions", json={
            "model": "code-intelligence",
            "messages": [{"role": "user", "content": "ciao"}],
        })
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "upstream_error"


# ── Streaming (G2) ────────────────────────────────────────────────────────────

# A canonical upstream IntelligenceSuite SSE stream.
_UPSTREAM_SSE = (
    'data: {"type": "sources", "sources": []}\n\n'
    'data: {"type": "token", "token": "Ciao"}\n\n'
    'data: {"type": "token", "token": " mondo"}\n\n'
    'data: {"type": "meta", "confidence": 0.9, "backend": "ollama", "escalated": false}\n\n'
    'data: {"type": "done"}\n\n'
)


def _streaming_app(captured: list, *, sse: str = _UPSTREAM_SSE, stream_status: int = 200):
    """App whose upstream returns SSE on /api/v1/stream, JSON elsewhere."""
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path == "/api/v1/stream":
            return httpx.Response(
                stream_status,
                content=sse.encode(),
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json=_QR)
    return build_app(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def _data_payloads(text: str) -> list[str]:
    return [line[len("data: "):] for line in text.splitlines() if line.startswith("data: ")]


def test_streaming_basic_flow():
    captured: list = []
    with TestClient(_streaming_app(captured)) as c:
        r = c.post("/v1/chat/completions", json={
            "model": "code-intelligence",
            "stream": True,
            "messages": [{"role": "user", "content": "saluta"}],
        })
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["X-IS-Module"] == "code-intelligence"
    # upstream hit the streaming endpoint
    assert captured[0].url.path == "/api/v1/stream"

    payloads = _data_payloads(r.text)
    assert payloads[-1] == "[DONE]"

    chunks = [json.loads(p) for p in payloads if p != "[DONE]"]
    # first chunk announces the assistant role
    assert chunks[0]["choices"][0]["delta"] == {"role": "assistant"}
    # reassembled text
    content = "".join(
        ch["choices"][0]["delta"].get("content", "") for ch in chunks
    )
    assert content == "Ciao mondo"
    # a terminal stop chunk exists
    assert any(ch["choices"][0]["finish_reason"] == "stop" for ch in chunks)
    # every chunk is a proper chunk object
    assert all(ch["object"] == "chat.completion.chunk" for ch in chunks)


def test_streaming_surfaces_upstream_error_event():
    captured: list = []
    sse = (
        'data: {"type": "token", "token": "parziale"}\n\n'
        'data: {"type": "error", "error": "boom"}\n\n'
    )
    with TestClient(_streaming_app(captured, sse=sse)) as c:
        r = c.post("/v1/chat/completions", json={
            "model": "doc-intelligence",
            "stream": True,
            "messages": [{"role": "user", "content": "x"}],
        })
    text = r.text
    assert "boom" in text
    assert _data_payloads(text)[-1] == "[DONE]"


def test_streaming_upstream_http_error_still_closes():
    captured: list = []
    with TestClient(_streaming_app(captured, stream_status=500)) as c:
        r = c.post("/v1/chat/completions", json={
            "model": "code-intelligence",
            "stream": True,
            "messages": [{"role": "user", "content": "x"}],
        })
    assert r.status_code == 200  # stream already started → 200 with error text inside
    payloads = _data_payloads(r.text)
    assert payloads[-1] == "[DONE]"
    assert any("upstream error 500" in p for p in payloads)
