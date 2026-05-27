"""AgentIntelligence stub — v0.4.x placeholder, full implementation in v0.5.0.

When the intent classifier routes to AGENT and intent_agent_enabled=False (default),
the routing layer already falls back to RAG before reaching this module.
This stub exists to:
  - Provide a valid ai-serve entry point for the launcher
  - Serve /health on :8084 so the launcher can show the "coming soon" card
  - Return a RAG-delegated response if called directly
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from intelligence_core.config import settings


def run_agent(question: str, **kwargs) -> dict:
    """Stub for AgentIntelligence. Delegates to RAG. Full impl in v0.5.0."""
    return {
        "answer": "[Agent non ancora disponibile — risposta RAG] " + question,
        "intent": "agent_stub",
        "iterations": 0,
    }


def build_app() -> FastAPI:
    app = FastAPI(title="AgentIntelligence (stub)", version="0.4.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "stub", "module": "agent", "version": "0.4.0"}

    @app.post("/api/v1/query")
    def query(body: dict):
        question = body.get("question", "")
        return run_agent(question)

    return app


app = build_app()


def main():
    uvicorn.run(
        "AgentIntelligence.agent_stub:app",
        host=settings.api_host,
        port=settings.agent_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
