"""SkillIntelligence FastAPI server — procedural guidance on port 8083."""

from __future__ import annotations

import logging
import time as _time
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from intelligence_core.config import settings
from intelligence_core.llm import get_llm_provider
from intelligence_core.server_base import QueryResponse as _QueryResponse
from SkillIntelligence.registry import get_registry

logger = logging.getLogger(__name__)


# ── Pydantic request/response models ─────────────────────────────────────────

class SkillQueryRequest(BaseModel):
    question:  str
    top_k:     int        = 5
    domain:    str | None = None
    min_score: float      = 0.3
    history:   list[dict] = []


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
    from SkillIntelligence.executor import SkillExecutor

    app = FastAPI(title="SkillIntelligence Server", version="0.3.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/docs")

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

    # ── /api/v1/query — unified entry point with intent routing ───────────────
    @app.post("/api/v1/query", response_model=_QueryResponse)
    def skill_query(req: SkillQueryRequest):
        from intelligence_core.config import settings
        from intelligence_core.intent import classify_intent, IntentLevel
        t0 = _time.perf_counter()

        if not settings.intent_routing:
            return _QueryResponse(
                answer="Usa /api/v1/skill/start per avviare una skill direttamente.",
                sources=[], intent="rag",
                confidence=0.0, escalated=False,
                backend=llm.backend_name,
                latency_ms=round((_time.perf_counter() - t0) * 1000, 1),
            )

        try:
            intent = classify_intent(req.question, registry=registry)
        except Exception as exc:
            logger.warning("SkillServer: classify_intent error: %s", exc)
            return _QueryResponse(
                answer="Errore nella classificazione dell'intent.",
                sources=[], intent="rag",
                confidence=0.0, escalated=False,
                backend=llm.backend_name,
                latency_ms=round((_time.perf_counter() - t0) * 1000, 1),
            )

        if intent.level != IntentLevel.SKILL or intent.skill_name is None:
            return _QueryResponse(
                answer="Nessuna skill corrispondente trovata per questa query.",
                sources=[], intent="rag",
                confidence=round(intent.confidence, 4), escalated=False,
                backend=llm.backend_name,
                latency_ms=round((_time.perf_counter() - t0) * 1000, 1),
            )

        skill_obj = registry.get_skill(intent.skill_name)
        if skill_obj is None:
            return _QueryResponse(
                answer=f"Skill '{intent.skill_name}' non trovata.",
                sources=[], intent="rag",
                confidence=0.0, escalated=False,
                backend=llm.backend_name,
                latency_ms=round((_time.perf_counter() - t0) * 1000, 1),
            )

        if not intent.parameters_complete:
            missing = [
                p for p, spec in skill_obj.parameters.items()
                if spec.get("required") and p not in intent.skill_parameters
            ]
            q_text = (
                f"Per guidarti nel processo '{intent.skill_name}' ho bisogno di sapere: "
                + ", ".join(f"**{p}**" for p in missing) + "."
            )
            if "environment" in missing:
                q_text += " (es: staging o production)"
            return _QueryResponse(
                answer=q_text, sources=[], intent="skill",
                confidence=round(intent.confidence, 4), escalated=False,
                backend=llm.backend_name,
                latency_ms=round((_time.perf_counter() - t0) * 1000, 1),
            )

        try:
            session_id, first_step = executor.start_session(skill_obj, intent.skill_parameters)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        answer = f"**{first_step.title}**\n\n{first_step.guidance}"
        if first_step.sources:
            answer += "\n\n_Fonti: " + ", ".join(
                s["source"] for s in first_step.sources if s.get("source")
            ) + "_"
        return _QueryResponse(
            answer=answer,
            sources=first_step.sources,
            confidence=round(intent.confidence, 4),
            escalated=False,
            backend=llm.backend_name,
            latency_ms=round((_time.perf_counter() - t0) * 1000, 1),
            intent="skill",
            session_id=session_id,
            is_last_step=first_step.is_last_step,
        )

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
