"""AgentIntelligence — tool definitions and executors for the ReAct agent.

Three retrieval tools expose the existing knowledge bases as callable functions:
  - search_code      → CodeIntelligence  (collection: code_intelligence)
  - search_docs      → DocIntelligence   (collection: doc_intelligence)
  - search_practices → MentorIntelligence (collection: mentor_intelligence)

Retrievers are lazy-loaded via Retriever.load_default() and cached per collection.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Tool schema (OpenAI function-calling format) ──────────────────────────────

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "Search the code knowledge base for relevant source code: "
                "classes, functions, modules, implementations. "
                "Use for questions about how something is implemented, "
                "which file contains X, or what a function does."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": (
                "Search the documentation knowledge base: PDF, DOCX, XLSX, Markdown. "
                "Use for questions about configuration, deployment, APIs, "
                "specifications, architecture decisions, or technical guides."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_practices",
            "description": (
                "Search the team practices and onboarding knowledge base. "
                "Use for questions about processes, conventions, best practices, "
                "team workflows, or onboarding procedures."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_impact",
            "description": (
                "Analyze the blast radius of changing a function or class using "
                "the code dependency graph. Returns direct callers, the total "
                "number of affected functions, the impacted files, and a risk "
                "level. Use before refactoring or to answer 'what breaks if I "
                "change X' and 'who calls X'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "function_name": {
                        "type": "string",
                        "description": "Name of the function or class to analyze",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Caller traversal depth (default 3)",
                        "default": 3,
                    },
                },
                "required": ["function_name"],
            },
        },
    },
]

# ── Collection mapping ────────────────────────────────────────────────────────

_COLLECTION_MAP: dict[str, str] = {
    "search_code":      "code_intelligence",
    "search_docs":      "doc_intelligence",
    "search_practices": "mentor_intelligence",
}

# ── Lazy retriever cache ──────────────────────────────────────────────────────

_retrievers: dict[str, Any] = {}


def _get_retriever(collection: str) -> Any | None:
    """Lazy-load and cache a Retriever for the given ChromaDB collection."""
    if collection not in _retrievers:
        try:
            from intelligence_core.retriever import Retriever
            _retrievers[collection] = Retriever.load_default(collection)
            logger.info("AgentTools: retriever '%s' caricato", collection)
        except Exception as exc:
            logger.warning(
                "AgentTools: impossibile caricare retriever '%s': %s", collection, exc
            )
            _retrievers[collection] = None
    return _retrievers[collection]


# ── Tool executor ─────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> dict:
    """Execute a tool by name with the given arguments.

    Returns a dict with ``results`` (list of chunks) or ``error`` /
    ``note`` on failure — never raises.
    """
    if name == "analyze_impact":
        return _execute_analyze_impact(args)

    collection = _COLLECTION_MAP.get(name)
    if collection is None:
        logger.warning("AgentTools: tool sconosciuto '%s'", name)
        return {"results": [], "error": f"Tool '{name}' non riconosciuto"}

    query = str(args.get("query", "")).strip()
    if not query:
        return {"results": [], "error": "Il parametro 'query' è obbligatorio"}

    top_k = int(args.get("top_k", 5))

    retriever = _get_retriever(collection)
    if retriever is None:
        return {
            "results": [],
            "note": (
                f"Knowledge base '{collection}' non disponibile — "
                "verifica che il modulo sia stato indicizzato (embed command)."
            ),
        }

    try:
        results = retriever.search(query, top_k=top_k)
        return {
            "results": [
                {
                    "text":   r.chunk.get("text", "")[:600],
                    "source": r.chunk.get("source", r.chunk.get("file_path", "")),
                    "score":  round(r.score, 3),
                }
                for r in results
            ],
        }
    except Exception as exc:
        logger.warning("AgentTools: tool '%s' fallito: %s", name, exc)
        return {"results": [], "error": str(exc)}


def _execute_analyze_impact(args: dict) -> dict:
    """Run dependency-graph impact analysis for a function/class."""
    function_name = str(args.get("function_name", "")).strip()
    if not function_name:
        return {"error": "Il parametro 'function_name' è obbligatorio"}

    depth = int(args.get("depth", 3))

    try:
        from intelligence_core.graph.store import graph_exists
        if not graph_exists("code"):
            return {
                "note": (
                    "Grafo delle dipendenze non disponibile — "
                    "esegui: ci-graph --domain code"
                ),
            }
        from intelligence_core.graph.retriever import GraphRetriever
        return GraphRetriever("code").impact_analysis(function_name, depth=depth)
    except Exception as exc:
        logger.warning("AgentTools: analyze_impact fallito: %s", exc)
        return {"error": str(exc)}
