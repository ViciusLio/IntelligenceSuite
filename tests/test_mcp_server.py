"""Tests for the IntelligenceSuite MCP server (intelligence_mcp).

Deterministic: the heavy retriever path is never exercised here. We test the
schema translation, the result formatting for every shape ``execute_tool`` can
return, the handler wiring, and the two real ``execute_tool`` paths that degrade
*before* touching ChromaDB (unknown tool / empty query).
"""

from __future__ import annotations

import contextlib

import pytest

pytest.importorskip("mcp", reason="Requires: pip install intelligence-suite[mcp]")

import anyio  # noqa: E402
import mcp.types as types  # noqa: E402

import intelligence_mcp.server as srv  # noqa: E402


# ── Package import-safety ─────────────────────────────────────────────────────

def test_package_lazy_main_export():
    import intelligence_mcp

    assert callable(intelligence_mcp.main)


def test_package_unknown_attr_raises():
    import intelligence_mcp

    with pytest.raises(AttributeError):
        _ = intelligence_mcp.does_not_exist


# ── Tool catalogue ────────────────────────────────────────────────────────────

def test_build_tool_list_translates_all_tools():
    tools = srv.build_tool_list()
    names = {t.name for t in tools}
    assert {"search_code", "search_docs", "search_practices", "analyze_impact"} == names
    for t in tools:
        assert isinstance(t, types.Tool)
        assert t.name and t.description
        assert isinstance(t.inputSchema, dict) and t.inputSchema.get("type") == "object"


# ── Result formatting (every execute_tool shape) ──────────────────────────────

def test_format_results_with_chunks():
    out = srv.format_results(
        "search_code",
        {"results": [{"text": "hello world", "source": "a.py", "score": 0.91}]},
    )
    assert len(out) == 1 and isinstance(out[0], types.TextContent)
    assert "[a.py] (score: 0.91)" in out[0].text
    assert "hello world" in out[0].text


def test_format_results_empty_with_note():
    out = srv.format_results("search_docs", {"results": [], "note": "KB not indexed"})
    assert out[0].text == "KB not indexed"


def test_format_results_empty_no_note():
    out = srv.format_results("search_docs", {"results": []})
    assert out[0].text == "No results found."


def test_format_results_error():
    out = srv.format_results("search_code", {"error": "boom"})
    assert "error: boom" in out[0].text


def test_format_results_note_only():
    out = srv.format_results("analyze_impact", {"note": "graph missing"})
    assert out[0].text == "graph missing"


def test_format_results_structured_payload():
    out = srv.format_results("analyze_impact", {"risk": "high", "direct_callers": ["f"]})
    assert '"risk": "high"' in out[0].text


def test_format_results_non_dict():
    out = srv.format_results("x", "raw string")
    assert out[0].text == "raw string"


# ── Handler registration & coroutines ─────────────────────────────────────────

def test_handlers_registered():
    assert types.ListToolsRequest in srv.server.request_handlers
    assert types.CallToolRequest in srv.server.request_handlers


def test_list_tools_handler():
    out = anyio.run(srv._handle_list_tools)
    assert {t.name for t in out} == {
        "search_code",
        "search_docs",
        "search_practices",
        "analyze_impact",
    }


def test_call_tool_handler_wiring(monkeypatch):
    captured = {}

    def fake_execute(name, args):
        captured["name"], captured["args"] = name, args
        return {"results": [{"text": "T", "source": "s.py", "score": 1.0}]}

    monkeypatch.setattr(srv, "execute_tool", fake_execute)

    async def _call():
        return await srv._handle_call_tool("search_code", {"query": "x", "top_k": 3})

    out = anyio.run(_call)
    assert captured == {"name": "search_code", "args": {"query": "x", "top_k": 3}}
    assert "T" in out[0].text


def test_call_tool_none_arguments(monkeypatch):
    monkeypatch.setattr(srv, "execute_tool", lambda name, args: {"results": [], "note": "ok"})

    async def _call():
        return await srv._handle_call_tool("search_code", None)

    out = anyio.run(_call)
    assert out[0].text == "ok"


# ── Real execute_tool paths that degrade before hitting ChromaDB ──────────────

def test_call_tool_unknown_tool_real():
    async def _call():
        return await srv._handle_call_tool("nope", {"query": "x"})

    out = anyio.run(_call)
    assert "error" in out[0].text.lower()


def test_call_tool_empty_query_real():
    async def _call():
        return await srv._handle_call_tool("search_code", {"query": "   "})

    out = anyio.run(_call)
    assert "query" in out[0].text.lower()


# ── Entry point wiring (stdio mocked — no real transport) ─────────────────────

def test_serve_runs_with_mocked_stdio(monkeypatch):
    ran = {}

    @contextlib.asynccontextmanager
    async def fake_stdio():
        yield ("READ", "WRITE")

    async def fake_run(read, write, init_opts):
        ran["streams"] = (read, write)

    import mcp.server.stdio as stdio_mod

    monkeypatch.setattr(stdio_mod, "stdio_server", fake_stdio)
    monkeypatch.setattr(srv.server, "run", fake_run)

    anyio.run(srv._serve)
    assert ran["streams"] == ("READ", "WRITE")


def test_main_invokes_anyio_run(monkeypatch):
    # anyio is imported lazily inside main(); patch the shared module object so
    # the server never actually starts on stdio during the test.
    calls = {}
    import anyio as anyio_mod

    monkeypatch.setattr(anyio_mod, "run", lambda fn: calls.setdefault("fn", fn))
    srv.main()
    assert callable(calls["fn"])
