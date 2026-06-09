"""MCP stdio server exposing IntelligenceSuite knowledge bases as tools.

Design
------
This is a *thin adapter*. The tool catalogue and the execution logic are reused
verbatim from ``AgentIntelligence.tools`` (the same ones the in-process ReAct
agent uses), so there is a single source of truth:

    MCP list_tools()  ←  TOOLS         (OpenAI function schema → MCP inputSchema)
    MCP call_tool()   ←  execute_tool  (returns dicts, never raises)

The LLM lives in the *client* (Claude Code / Cursor / Claude Desktop). This
server performs retrieval only — it never holds model keys nor dumps settings.

Transport is stdio: the JSON-RPC channel IS stdout, so all logging must go to
stderr and no library may print to stdout (see ``main``).

Tenancy: the ChromaDB collection is resolved at call time via
``intelligence_core.paths``, which honours the ``IS_PROJECT`` env var — set it
in the client's MCP server config to isolate a project's data.

Optional dependency:  pip install intelligence-suite[mcp]
"""

from __future__ import annotations

import json
import logging
import os
import sys

# chromadb (imported lazily by the retriever on first call) emits telemetry;
# silence it before it can ever touch stdout. setdefault → user override wins.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

logger = logging.getLogger(__name__)

try:
    import mcp.types as types
    from mcp.server import Server
except ImportError as e:  # pragma: no cover - exercised via monkeypatch in tests
    raise ImportError(
        "Optional dependency missing. Install with: "
        "pip install intelligence-suite[mcp]"
    ) from e

from AgentIntelligence.tools import TOOLS, execute_tool

SERVER_NAME = "intelligence-suite"

server: Server = Server(SERVER_NAME)


# ── Pure helpers (sync, no event loop — unit-testable) ────────────────────────

def build_tool_list() -> list[types.Tool]:
    """Translate the shared OpenAI-format ``TOOLS`` into MCP ``Tool`` objects.

    The OpenAI ``function.parameters`` JSON schema maps 1:1 onto MCP
    ``inputSchema``, so no schema is hand-maintained twice.
    """
    tools: list[types.Tool] = []
    for entry in TOOLS:
        fn = entry["function"]
        tools.append(
            types.Tool(
                name=fn["name"],
                description=fn["description"],
                inputSchema=fn["parameters"],
            )
        )
    return tools


def format_results(name: str, result: dict) -> list[types.TextContent]:
    """Render an ``execute_tool`` result dict as MCP text content.

    Handles the three shapes ``execute_tool`` can return — ``results`` (list of
    retrieval chunks), ``note`` (graceful degradation), ``error`` — plus the
    structured dict returned by ``analyze_impact``.
    """
    if not isinstance(result, dict):
        return [types.TextContent(type="text", text=str(result))]

    if result.get("error"):
        return [types.TextContent(type="text", text=f"Tool '{name}' error: {result['error']}")]

    if "results" in result:
        rows = result.get("results") or []
        if not rows:
            note = result.get("note") or "No results found."
            return [types.TextContent(type="text", text=note)]
        parts = [
            f"[{r.get('source', '')}] (score: {r.get('score', '')})\n{r.get('text', '')}"
            for r in rows
        ]
        return [types.TextContent(type="text", text="\n\n---\n\n".join(parts))]

    if result.get("note"):
        return [types.TextContent(type="text", text=result["note"])]

    # analyze_impact and any other structured payload
    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


# ── MCP handlers ──────────────────────────────────────────────────────────────

@server.list_tools()
async def _handle_list_tools() -> list[types.Tool]:
    return build_tool_list()


@server.call_tool()
async def _handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    logger.info("MCP call_tool: %s args=%s", name, arguments)
    result = execute_tool(name, arguments or {})
    return format_results(name, result)


# ── Entry point ───────────────────────────────────────────────────────────────

async def _serve() -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Console-script entry point (``is-mcp``). Runs the stdio server."""
    # CRITICAL: logging must go to stderr — stdout is the JSON-RPC transport.
    logging.basicConfig(
        level=os.environ.get("IS_MCP_LOG_LEVEL", "INFO"),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("Starting IntelligenceSuite MCP server (stdio) - %d tools", len(TOOLS))

    import anyio

    anyio.run(_serve)


if __name__ == "__main__":  # pragma: no cover
    main()
