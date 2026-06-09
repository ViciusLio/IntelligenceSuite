"""intelligence_mcp — Model Context Protocol server for IntelligenceSuite.

Exposes the on-premise knowledge bases (code, docs, practices, dependency graph)
as MCP tools to any MCP-compatible client (Claude Code, Cursor, Claude Desktop).

This is a thin adapter over ``AgentIntelligence.tools`` — the same tool schemas
and executor used by the in-process ReAct agent — so there is a single source of
truth for what the tools do. The LLM lives in the *client*: this server performs
retrieval only, never holds model keys or dumps configuration.

Optional dependency: ``pip install intelligence-suite[mcp]``
"""

from __future__ import annotations

__all__ = ["main"]


def __getattr__(name: str):  # pragma: no cover - thin lazy re-export
    # Lazy so that ``import intelligence_mcp`` never pulls in the optional ``mcp``
    # dependency until the server is actually started.
    if name == "main":
        from intelligence_mcp.server import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
