"""Gestisce lo stato della sessione di onboarding per utente."""

from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DIR = Path(".mentor_sessions")


@dataclass
class OnboardingSession:
    session_id:      str
    user_name:       str
    profile:         str
    current_step:    int = 0
    completed_steps: list[str] = field(default_factory=list)
    skipped_steps:   list[str] = field(default_factory=list)
    questions_asked: list[dict] = field(default_factory=list)
    started_at:      str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_active:     str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    feedback:        list[dict] = field(default_factory=list)


def create_session(user_name: str, profile: str) -> OnboardingSession:
    return OnboardingSession(
        session_id=str(uuid.uuid4()),
        user_name=user_name,
        profile=profile,
    )


def save_session(session: OnboardingSession) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"{session.session_id}.json"
    session.last_active = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(asdict(session), ensure_ascii=False, indent=2), encoding="utf-8")


def load_session(session_id: str) -> OnboardingSession:
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Sessione non trovata: {session_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return OnboardingSession(**data)


def mark_step_complete(session: OnboardingSession, step_id: str) -> None:
    if step_id not in session.completed_steps:
        session.completed_steps.append(step_id)
    session.current_step += 1


def record_question(
    session: OnboardingSession,
    query: str,
    answer_summary: str,
    sources: list[str],
) -> None:
    session.questions_asked.append({
        "query":          query,
        "answer_summary": answer_summary,
        "sources":        sources,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
    })


def record_feedback(
    session: OnboardingSession,
    step_id: str,
    rating: int,
    note: str = "",
) -> None:
    session.feedback.append({
        "step_id":   step_id,
        "rating":    max(1, min(5, rating)),
        "note":      note,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
