"""SkillIntelligence FastAPI server — procedural guidance on port 8083."""

from __future__ import annotations

import logging
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from intelligence_core.config import settings
from intelligence_core.llm import get_llm_provider

logger = logging.getLogger(__name__)


# ── Pydantic request/response models ─────────────────────────────────────────

class StartRequest(BaseModel):
    skill_name: str
    parameters: dict = {}


class NextRequest(BaseModel):
    session_id: str
    user_input: str | None = None


class SkillResultResponse(BaseModel):
    step_id: str
    title: str
    guidance: str
    sources: list[dict]
    requires_confirmation: bool
    is_last_step: bool
    session_id: str


class StartResponse(BaseModel):
    session_id: str
    step: SkillResultResponse


class NextResponse(BaseModel):
    step: SkillResultResponse | None
    completed: bool


# ── App factory ───────────────────────────────────────────────────────────────

def build_app() -> FastAPI:
    from SkillIntelligence.registry import get_registry
    from SkillIntelligence.executor import SkillExecutor

    app = FastAPI(title="SkillIntelligence Server", version="0.3.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Load registry once at startup
    registry = get_registry()
    llm = get_llm_provider()
    executor = SkillExecutor(llm=llm)

    # ── Health ─────────────────────────────────────────────────────────────────
    @app.get("/health")
    def health():
        return {
            "status":        "ok",
            "module":        "skill",
            "skills_count":  registry.count(),
            "llm_backend":   llm.backend_name,
            "llm_available": llm.is_available(),
        }

    # ── List skills ────────────────────────────────────────────────────────────
    @app.get("/api/v1/skill/list")
    def list_skills():
        return {"skills": registry.list_skills()}

    # ── Start session ──────────────────────────────────────────────────────────
    @app.post("/api/v1/skill/start", response_model=StartResponse)
    def start_session(req: StartRequest):
        skill = registry.get_skill(req.skill_name)
        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{req.skill_name}' non trovata")

        try:
            session_id, result = executor.start_session(skill, req.parameters)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        return StartResponse(
            session_id=session_id,
            step=SkillResultResponse(**result.__dict__),
        )

    # ── Next step ──────────────────────────────────────────────────────────────
    @app.post("/api/v1/skill/next", response_model=NextResponse)
    def next_step(req: NextRequest):
        try:
            result = executor.next_step(req.session_id, req.user_input)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

        if result is None:
            return NextResponse(step=None, completed=True)
        return NextResponse(
            step=SkillResultResponse(**result.__dict__),
            completed=False,
        )

    # ── Session info ───────────────────────────────────────────────────────────
    @app.get("/api/v1/skill/session/{session_id}")
    def session_info(session_id: str):
        try:
            return executor.get_session_info(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    return app


app = build_app()


def main():
    port = getattr(settings, "si_port", 8083)
    uvicorn.run(
        "SkillIntelligence.skill_server:app",
        host=settings.api_host,
        port=port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
