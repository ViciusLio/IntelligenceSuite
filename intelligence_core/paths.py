"""Project-aware collection names and state-directory paths.

All helpers read IS_PROJECT at *call time* so they work correctly with
monkeypatching in tests and with environment overrides at startup.

IS_PROJECT="default"  → legacy layout, unchanged:
    chroma_persist_dir from settings (honours CHROMA_PERSIST_DIR override)
    graph / eval / skill_sessions under ~/.intelligence_suite/

IS_PROJECT="acme"     → isolated layout:
    chroma  under ~/.intelligence_suite/acme/chroma/
    graph   under ~/.intelligence_suite/acme/graph/
    eval    under ~/.intelligence_suite/acme/eval/
    sessions under ~/.intelligence_suite/acme/skill_sessions/
    collections prefixed:  acme_code_intelligence, acme_doc_intelligence, …
"""

from __future__ import annotations
from pathlib import Path

_IS_BASE = Path.home() / ".intelligence_suite"

_COLLECTIONS: dict[str, str] = {
    "code":   "code_intelligence",
    "doc":    "doc_intelligence",
    "mentor": "mentor_intelligence",
    "qa":     "proposal_intelligence",
}


def _project() -> str:
    from intelligence_core.config import settings
    return settings.is_project


def collection_name(domain: str) -> str:
    """Return the ChromaDB collection name for *domain*, prefixed when IS_PROJECT != 'default'."""
    base = _COLLECTIONS.get(domain, domain)
    p = _project()
    return base if p == "default" else f"{p}_{base}"


def state_dir() -> Path:
    """Root state directory for the current project."""
    p = _project()
    return _IS_BASE if p == "default" else _IS_BASE / p


def chroma_dir() -> Path:
    """ChromaDB persist directory for the current project.

    For the default project honours the CHROMA_PERSIST_DIR env-var override.
    """
    p = _project()
    if p == "default":
        from intelligence_core.config import settings
        return Path(settings.chroma_persist_dir)
    return state_dir() / "chroma"


def graph_dir() -> Path:
    return state_dir() / "graph"


def eval_dir() -> Path:
    return state_dir() / "eval"


def skill_sessions_dir() -> Path:
    return state_dir() / "skill_sessions"
