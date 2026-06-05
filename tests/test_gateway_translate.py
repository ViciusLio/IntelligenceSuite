"""Unit tests for intelligence_gateway.translate — pure, no network, no servers.

Covers:
  * model resolution (concrete / auto / unknown)
  * auto-routing heuristic (strategy A)
  * upstream URL building from a settings-like object
  * OpenAI request  → IS /api/v1/query body
  * IS QueryResponse → OpenAI chat.completion
  * IS SSE event     → OpenAI chat.completion.chunk
  * SSE wire helpers (format / parse round-trip)
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from intelligence_gateway import translate as T


# ── Model resolution ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("model_id", list(T.MODULES.keys()))
def test_resolve_concrete_model(model_id):
    route = T.resolve_model(model_id, "qualunque domanda")
    assert route.model_id == model_id
    assert route.port_setting.endswith("_port")


def test_resolve_auto_model_returns_a_concrete_module():
    route = T.resolve_model(T.AUTO_MODEL, "spiegami questa funzione Python")
    assert route.model_id in T.MODULES


def test_resolve_unknown_model_raises_keyerror():
    with pytest.raises(KeyError):
        T.resolve_model("gpt-4o", "ciao")


# ── Auto-routing heuristic ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "question, expected",
    [
        ("Perché questa funzione lancia un'eccezione nello stacktrace?", "code-intelligence"),
        ("Cosa dice il capitolo 3 del documento PDF allegato?",          "doc-intelligence"),
        ("Sono un nuovo junior, come inizio l'onboarding?",              "mentor-intelligence"),
        ("Compila il questionario di gara con la nostra offerta",        "proposal-intelligence"),
    ],
)
def test_route_module_heuristic(question, expected):
    assert T.route_module(question) == expected


def test_route_module_defaults_when_no_signal():
    assert T.route_module("buongiorno") == T.DEFAULT_MODULE


def test_route_module_handles_empty():
    assert T.route_module("") == T.DEFAULT_MODULE


# ── Upstream URL ──────────────────────────────────────────────────────────────

def _fake_settings(**kw):
    base = dict(ci_port=8080, di_port=8081, mi_port=8082, pi_port=8085)
    base.update(kw)
    return SimpleNamespace(**base)


def test_upstream_base_url_default_host():
    route = T.MODULES["code-intelligence"]
    assert T.upstream_base_url(route, _fake_settings()) == "http://localhost:8080"


def test_upstream_base_url_explicit_host_wins():
    route = T.MODULES["doc-intelligence"]
    url = T.upstream_base_url(route, _fake_settings(), host="doc-svc")
    assert url == "http://doc-svc:8081"


def test_upstream_base_url_settings_host():
    route = T.MODULES["mentor-intelligence"]
    s = _fake_settings(gw_upstream_host="mentor-svc")
    assert T.upstream_base_url(route, s) == "http://mentor-svc:8082"


# ── /v1/models ────────────────────────────────────────────────────────────────

def test_list_models_shape():
    models = T.list_models()
    ids = {m["id"] for m in models}
    assert ids == set(T.MODULES) | {T.AUTO_MODEL}
    for m in models:
        assert m["object"] == "model"
        assert "name" in m


# ── OpenAI request → IS body ──────────────────────────────────────────────────

def test_split_messages_extracts_last_user_and_history():
    messages = [
        {"role": "system",    "content": "sei un assistente"},
        {"role": "user",      "content": "prima domanda"},
        {"role": "assistant", "content": "prima risposta"},
        {"role": "user",      "content": "seconda domanda"},
    ]
    question, history = T.split_messages(messages)
    assert question == "seconda domanda"
    assert history == [
        {"role": "user",      "content": "prima domanda"},
        {"role": "assistant", "content": "prima risposta"},
    ]
    # system message dropped
    assert all(m["role"] != "system" for m in history)


def test_split_messages_empty():
    assert T.split_messages([]) == ("", [])


def test_split_messages_coerces_list_content():
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "riga uno"},
            {"type": "text", "text": "riga due"},
        ],
    }]
    question, _ = T.split_messages(messages)
    assert question == "riga uno\nriga due"


def test_openai_to_is_request_concrete():
    body = {
        "model": "code-intelligence",
        "messages": [{"role": "user", "content": "dov'è la classe Retriever?"}],
    }
    route, is_body = T.openai_to_is_request(body)
    assert route.model_id == "code-intelligence"
    assert is_body["question"] == "dov'è la classe Retriever?"
    assert is_body["history"] == []
    assert is_body["domain"] is None
    assert "top_k" in is_body and "min_score" in is_body


def test_openai_to_is_request_auto_routes():
    body = {
        "model": "intelligence-suite",
        "messages": [{"role": "user", "content": "come inizio l'onboarding da junior?"}],
    }
    route, _ = T.openai_to_is_request(body)
    assert route.model_id == "mentor-intelligence"


def test_openai_to_is_request_unknown_model_raises():
    with pytest.raises(KeyError):
        T.openai_to_is_request({"model": "llama3", "messages": []})


def test_openai_to_is_request_proposal_uses_standard_body():
    # ProposalIntelligence now exposes the standard single-question contract,
    # so the gateway treats it like any other module (no special body).
    body = {
        "model": "proposal-intelligence",
        "messages": [{"role": "user", "content": "Rispondi al requisito di gara"}],
    }
    route, is_body = T.openai_to_is_request(body)
    assert route.model_id == "proposal-intelligence"
    assert is_body["question"] == "Rispondi al requisito di gara"
    assert is_body["history"] == []
    assert "top_k" in is_body and "min_score" in is_body


# ── IS response → OpenAI chat.completion ──────────────────────────────────────

def test_is_response_to_openai_shape():
    qr = {"answer": "ecco la risposta", "sources": [], "confidence": 0.9,
          "backend": "ollama", "latency_ms": 12.3}
    out = T.is_response_to_openai(qr, "code-intelligence", chat_id="chatcmpl-x", created=111)
    assert out["id"] == "chatcmpl-x"
    assert out["object"] == "chat.completion"
    assert out["created"] == 111
    assert out["model"] == "code-intelligence"
    choice = out["choices"][0]
    assert choice["index"] == 0
    assert choice["finish_reason"] == "stop"
    assert choice["message"] == {"role": "assistant", "content": "ecco la risposta"}
    assert set(out["usage"]) == {"prompt_tokens", "completion_tokens", "total_tokens"}


def test_is_response_to_openai_autogenerates_id():
    out = T.is_response_to_openai({"answer": "x"}, "doc-intelligence")
    assert out["id"].startswith("chatcmpl-")


# ── IS SSE event → OpenAI chunk ───────────────────────────────────────────────

def test_token_event_becomes_content_chunk():
    chunk = T.is_sse_event_to_openai_chunk(
        {"type": "token", "token": "ciao "},
        model="doc-intelligence", chat_id="chatcmpl-y", created=222,
    )
    assert chunk["object"] == "chat.completion.chunk"
    assert chunk["model"] == "doc-intelligence"
    assert chunk["choices"][0]["delta"] == {"content": "ciao "}
    assert chunk["choices"][0]["finish_reason"] is None


@pytest.mark.parametrize("event", [
    {"type": "sources", "sources": []},
    {"type": "meta", "confidence": 0.8, "backend": "ollama", "escalated": False},
    {"type": "done"},
    {"type": "error", "error": "boom"},
])
def test_non_token_events_return_none(event):
    assert T.is_sse_event_to_openai_chunk(
        event, model="m", chat_id="c", created=1
    ) is None


def test_chat_chunk_role_only_delta():
    chunk = T.chat_chunk(model="m", chat_id="c", created=1, role="assistant")
    assert chunk["choices"][0]["delta"] == {"role": "assistant"}


def test_chat_chunk_finish_stop():
    chunk = T.chat_chunk(model="m", chat_id="c", created=1, finish_reason="stop")
    assert chunk["choices"][0]["delta"] == {}
    assert chunk["choices"][0]["finish_reason"] == "stop"


# ── SSE wire helpers ──────────────────────────────────────────────────────────

def test_format_sse_dict():
    line = T.format_sse({"a": 1})
    assert line == 'data: {"a": 1}\n\n'


def test_format_sse_done_sentinel():
    assert T.format_sse("[DONE]") == "data: [DONE]\n\n"


def test_parse_sse_line_roundtrip():
    event = {"type": "token", "token": "x"}
    line = T.format_sse(event).rstrip("\n")
    assert T.parse_sse_line(line) == event


@pytest.mark.parametrize("line", ["", ": comment", "data: [DONE]", "data:", "event: ping"])
def test_parse_sse_line_non_data_returns_none(line):
    assert T.parse_sse_line(line) is None


def test_parse_sse_line_bad_json_returns_none():
    assert T.parse_sse_line("data: {not json}") is None
