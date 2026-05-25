"""Server MentorIntelligence — endpoint onboarding adattivo."""

from __future__ import annotations
import time
import logging
import uvicorn

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from intelligence_core.config import settings
from intelligence_core.embedder import get_embedder
from intelligence_core.store import ChromaStore
from intelligence_core.retriever import Retriever
from intelligence_core.server_base import create_app

from MentorIntelligence.profile_detector import detect_profile
from MentorIntelligence.session_manager import (
    create_session, load_session, save_session,
    mark_step_complete, record_feedback,
)
from MentorIntelligence.path_builder import (
    build_path, get_current_step, get_next_step, compute_progress,
)
from MentorIntelligence.orchestrator import MentorOrchestrator

logger = logging.getLogger(__name__)


# ── Request/Response models ──────────────────────────────────────────────────

class OnboardRequest(BaseModel):
    user_name: str
    role_hint: str = ""
    intro: str = ""


class OnboardResponse(BaseModel):
    session_id: str
    profile: str
    welcome_message: str
    first_step: dict
    suggested_first_question: str


class MentorQueryRequest(BaseModel):
    session_id: str
    question: str
    top_k: int = 5


class MentorQueryResponse(BaseModel):
    answer: str
    sources_by_domain: dict
    step_context: dict | None
    suggested_next: str | None
    progress: dict
    escalated: bool
    latency_ms: float


class ProgressResponse(BaseModel):
    session_id: str
    profile: str
    progress: dict
    completed_steps: list[str]
    current_step: dict | None
    next_step: dict | None


class FeedbackRequest(BaseModel):
    session_id: str
    step_id: str
    rating: int
    note: str = ""


# ── App factory ──────────────────────────────────────────────────────────────

def build_app() -> FastAPI:
    embedder = get_embedder()
    code_retriever   = Retriever(embedder=embedder, store=ChromaStore("code_intelligence"))
    doc_retriever    = Retriever(embedder=embedder, store=ChromaStore("doc_intelligence"))
    mentor_retriever = Retriever(embedder=embedder, store=ChromaStore("mentor_intelligence"))

    orchestrator = MentorOrchestrator(code_retriever, doc_retriever, mentor_retriever)

    base_retriever = Retriever(embedder=embedder, store=ChromaStore("mentor_intelligence"))
    app = create_app(title="MentorIntelligence Server", retriever=base_retriever)

    @app.post("/api/v1/mentor/onboard", response_model=OnboardResponse)
    def onboard(req: OnboardRequest):
        profile_result = detect_profile(req.intro, req.role_hint)
        session = create_session(req.user_name, profile_result.profile.value)
        save_session(session)

        path = build_path(session.profile)
        first_step = path[0] if path else {"title": "Benvenuto", "sources": [], "suggested_queries": []}
        suggested = first_step.get("suggested_queries", ["Come funziona questo progetto?"])[0]

        welcome = (
            f"Ciao {req.user_name}! "
            f"Ho rilevato il tuo profilo come '{profile_result.profile.value}' "
            f"(confidenza: {profile_result.confidence:.0%}). "
            f"Il tuo percorso ha {len(path)} passi. "
            f"Iniziamo da: {first_step.get('title', 'Introduzione')}."
        )

        return OnboardResponse(
            session_id=session.session_id,
            profile=session.profile,
            welcome_message=welcome,
            first_step=first_step,
            suggested_first_question=suggested,
        )

    @app.post("/api/v1/mentor/ask", response_model=MentorQueryResponse)
    def ask(req: MentorQueryRequest):
        try:
            session = load_session(req.session_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Sessione non trovata")

        t0 = time.perf_counter()
        result = orchestrator.query(req.question, session, top_k=req.top_k)
        save_session(session)

        progress = compute_progress(session)
        latency = (time.perf_counter() - t0) * 1000

        sources_serialized = {
            domain: [{"id": r.chunk.get("id"), "score": r.score, "source": r.chunk.get("source")}
                     for r in res_list]
            for domain, res_list in result.sources_by_domain.items()
        }

        return MentorQueryResponse(
            answer=result.answer,
            sources_by_domain=sources_serialized,
            step_context=result.step_context,
            suggested_next=result.suggested_next,
            progress=progress,
            escalated=False,
            latency_ms=latency,
        )

    @app.get("/api/v1/mentor/progress/{session_id}", response_model=ProgressResponse)
    def progress(session_id: str):
        try:
            session = load_session(session_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Sessione non trovata")

        return ProgressResponse(
            session_id=session.session_id,
            profile=session.profile,
            progress=compute_progress(session),
            completed_steps=session.completed_steps,
            current_step=get_current_step(session),
            next_step=get_next_step(session),
        )

    @app.post("/api/v1/mentor/complete/{session_id}/{step_id}")
    def complete_step(session_id: str, step_id: str):
        try:
            session = load_session(session_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Sessione non trovata")
        mark_step_complete(session, step_id)
        save_session(session)
        return {"ok": True, "progress": compute_progress(session)}

    @app.post("/api/v1/mentor/feedback")
    def feedback(req: FeedbackRequest):
        try:
            session = load_session(req.session_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Sessione non trovata")
        record_feedback(session, req.step_id, req.rating, req.note)
        save_session(session)
        return {"ok": True}

    @app.post("/api/v1/mentor/reset/{session_id}")
    def reset(session_id: str):
        try:
            session = load_session(session_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Sessione non trovata")
        session.current_step = 0
        session.completed_steps = []
        session.skipped_steps = []
        session.questions_asked = []
        save_session(session)
        return {"ok": True, "session_id": session_id}

    return app


app = build_app()


def main():
    uvicorn.run(
        "MentorIntelligence.mentor_server:app",
        host=settings.api_host,
        port=settings.mi_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
