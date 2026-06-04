"""AgentIntelligence FastAPI server — multi-hop ReAct agent on port 8084."""

from __future__ import annotations

import logging
import time as _time
import uvicorn

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from intelligence_core.config import settings
from intelligence_core.llm import get_llm_provider

logger = logging.getLogger(__name__)

# ── Runtime thinking toggle (overrides settings.thinking_mode at runtime) ─────
_thinking_enabled: bool = settings.thinking_mode


# ── Pydantic models ───────────────────────────────────────────────────────────

class AgentQueryRequest(BaseModel):
    question:    str
    history:     list[dict] = []


class AgentQueryResponse(BaseModel):
    answer:      str
    intent:      str        = "agent"
    iterations:  int        = 0
    reasoning:   str        = ""
    tools_used:  list[str]  = []
    backend:     str        = ""
    latency_ms:  float      = 0.0


class ThinkingToggleRequest(BaseModel):
    enabled: bool


class ThinkingToggleResponse(BaseModel):
    enabled: bool


# ── App factory ───────────────────────────────────────────────────────────────

def build_app() -> FastAPI:
    global _thinking_enabled
    from AgentIntelligence.agent import run_agent

    app = FastAPI(title="AgentIntelligence Server", version="0.5.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from intelligence_core.auth import add_auth_middleware, warn_if_key_missing
    add_auth_middleware(app)
    warn_if_key_missing()

    from intelligence_core.observability import add_metrics_endpoint
    add_metrics_endpoint(app)

    # ── Root redirect ──────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/docs")

    # ── Health ─────────────────────────────────────────────────────────────────
    @app.get("/health")
    def health():
        # NOTE: do NOT call llm.is_available() here — it makes a synchronous
        # HTTP request to the LLM server which can exceed the browser's 2s
        # fetch timeout, making the launcher card show "offline" even when
        # ai-serve is up and responding.
        llm = get_llm_provider()
        supports_tools = hasattr(llm, "generate_with_tools")
        return {
            "status":         "ok",
            "module":         "agent",
            "version":        "0.5.0",
            "llm_backend":    llm.backend_name,
            "thinking_mode":  _thinking_enabled,
            "supports_tools": supports_tools,
            "max_iterations": settings.agent_max_iterations,
        }

    # ── Thinking mode toggle ───────────────────────────────────────────────────
    @app.get("/api/v1/thinking", response_model=ThinkingToggleResponse)
    def get_thinking():
        return ThinkingToggleResponse(enabled=_thinking_enabled)

    @app.post("/api/v1/thinking", response_model=ThinkingToggleResponse)
    def set_thinking(req: ThinkingToggleRequest):
        global _thinking_enabled
        _thinking_enabled = req.enabled
        logger.info("AgentIntelligence: thinking mode impostato a %s", _thinking_enabled)
        return ThinkingToggleResponse(enabled=_thinking_enabled)

    # ── Query ──────────────────────────────────────────────────────────────────
    @app.post("/api/v1/query", response_model=AgentQueryResponse)
    def query(req: AgentQueryRequest):
        t0 = _time.perf_counter()
        llm = get_llm_provider()

        try:
            result = run_agent(
                question=req.question,
                llm=llm,
                max_iterations=settings.agent_max_iterations,
                thinking=_thinking_enabled,
            )
        except Exception as exc:
            logger.error("AgentIntelligence: run_agent fallito: %s", exc)
            result = {
                "answer":     f"[Agent error: {exc}]",
                "intent":     "agent_error",
                "iterations": 0,
                "reasoning":  "",
                "tools_used": [],
                "backend":    llm.backend_name,
            }

        latency_ms = round((_time.perf_counter() - t0) * 1000, 1)
        return AgentQueryResponse(latency_ms=latency_ms, **result)

    return app


app = build_app()


def main():
    port = getattr(settings, "agent_port", 8084)
    uvicorn.run(
        "AgentIntelligence.agent_server:app",
        host=settings.api_host,
        port=port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
