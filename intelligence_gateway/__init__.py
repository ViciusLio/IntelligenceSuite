"""IntelligenceSuite Gateway — OpenAI-compatible adapter.

Exposes a standard OpenAI Chat Completions API (`/v1/chat/completions`,
`/v1/models`) in front of the existing IntelligenceSuite module servers
(Code / Doc / Mentor / Proposal).

The gateway is a *thin protocol adapter*: it never re-implements retrieval,
intent routing, skills, agents or escalation — those already happen inside
each module server. It only translates OpenAI ↔ IntelligenceSuite and proxies
the request over HTTP.

This lets ANY OpenAI-speaking client (OpenWebUI, LibreChat, the openai SDK,
curl, IDE plugins) reuse IntelligenceSuite without bespoke integration.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
