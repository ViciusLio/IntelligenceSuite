"""Costruisce percorsi di onboarding adattivi per profilo."""

from __future__ import annotations
import json
from pathlib import Path

from MentorIntelligence.session_manager import OnboardingSession

TEMPLATES: dict = json.loads(
    (Path(__file__).parent / "content" / "path_templates.json").read_text(encoding="utf-8")
)


def build_path(profile: str) -> list[dict]:
    """Ritorna la sequenza base di step per il profilo dato."""
    entry = TEMPLATES.get(profile) or TEMPLATES.get("unknown", {})
    return list(entry.get("steps", []))


def get_current_step(session: OnboardingSession) -> dict | None:
    """Ritorna lo step corrente della sessione, None se completato."""
    path = build_path(session.profile)
    if session.current_step >= len(path):
        return None
    return path[session.current_step]


def get_next_step(session: OnboardingSession) -> dict | None:
    """Ritorna il prossimo step da fare."""
    path = build_path(session.profile)
    next_idx = session.current_step + 1
    if next_idx >= len(path):
        return None
    return path[next_idx]


def adapt_path(session: OnboardingSession, last_query: str) -> list[dict]:
    """
    Adatta il percorso in tempo reale basandosi sull'ultima domanda.
    Se l'utente anticipa un argomento di step futuri, segna quell'area come rilevante.
    """
    path = build_path(session.profile)
    query_lower = last_query.lower()

    for step in path[session.current_step + 1:]:
        for sq in step.get("suggested_queries", []):
            if any(word in query_lower for word in sq.lower().split() if len(word) > 3):
                step["anticipata"] = True
                break

    return path


def compute_progress(session: OnboardingSession) -> dict:
    """Ritorna: {completed, total, percent, current_step_title, next_step_title}"""
    path = build_path(session.profile)
    total = len(path)
    completed = len(session.completed_steps)
    percent = round(completed / total * 100, 1) if total > 0 else 0.0

    current = get_current_step(session)
    nxt = get_next_step(session)

    return {
        "completed":         completed,
        "total":             total,
        "percent":           percent,
        "current_step_title": current["title"] if current else None,
        "next_step_title":    nxt["title"] if nxt else None,
    }
