"""Rileva il profilo dell'utente per costruire il percorso adattivo."""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class Profile(str, Enum):
    DEVELOPER     = "developer"
    NON_DEVELOPER = "non_developer"
    MIXED         = "mixed"
    UNKNOWN       = "unknown"


@dataclass
class ProfileResult:
    profile: Profile
    confidence: float
    signals: list[str]


_DEV_SIGNALS = {
    "sviluppatore", "developer", "engineer", "backend", "frontend", "fullstack",
    "codice", "python", "java", "typescript", "golang", "go", "rust", "kotlin",
    "git", "api", "database", "sql", "kubernetes", "docker", "microservizi",
    "programmatore", "software", "tecnico", "devops", "cloud", "architettura",
    "testing", "debug", "refactoring", "framework",
}

_NON_DEV_SIGNALS = {
    "pm", "product manager", "hr", "commerciale", "operations", "manager",
    "marketing", "vendite", "sales", "contabile", "legale", "giuridico",
    "amministrativo", "business", "stakeholder", "roadmap", "budget",
    "progetto", "cliente", "ux", "designer", "data analyst", "analista",
    "non tecnico", "comunicazione", "formazione",
}


def detect_profile(intro_text: str, role_hint: str = "") -> ProfileResult:
    """
    Rileva il profilo dall'introduzione dell'utente.
    role_hint sovrascrive il rilevamento se valorizzato.
    """
    if role_hint:
        hint_lower = role_hint.lower().strip()
        if hint_lower in ("developer", "developer"):
            return ProfileResult(Profile.DEVELOPER, 1.0, [f"role_hint: {role_hint}"])
        if hint_lower in ("non_developer", "non developer", "pm", "hr"):
            return ProfileResult(Profile.NON_DEVELOPER, 1.0, [f"role_hint: {role_hint}"])
        if hint_lower == "mixed":
            return ProfileResult(Profile.MIXED, 1.0, [f"role_hint: {role_hint}"])

    text_lower = intro_text.lower()
    dev_found = [s for s in _DEV_SIGNALS if s in text_lower]
    non_dev_found = [s for s in _NON_DEV_SIGNALS if s in text_lower]

    dev_score = len(dev_found)
    non_dev_score = len(non_dev_found)

    if dev_score == 0 and non_dev_score == 0:
        return ProfileResult(Profile.UNKNOWN, 0.5, [])

    total = dev_score + non_dev_score

    if dev_score > 0 and non_dev_score > 0:
        ratio = dev_score / total
        if 0.3 <= ratio <= 0.7:
            confidence = 0.6 + abs(ratio - 0.5) * 0.4
            return ProfileResult(
                Profile.MIXED, round(confidence, 2),
                [f"dev={dev_found}", f"non_dev={non_dev_found}"],
            )
        if ratio > 0.7:
            return ProfileResult(
                Profile.DEVELOPER, round(ratio, 2),
                dev_found[:5],
            )
        return ProfileResult(
            Profile.NON_DEVELOPER, round(1 - ratio, 2),
            non_dev_found[:5],
        )

    if dev_score > 0:
        confidence = min(0.6 + dev_score * 0.1, 1.0)
        return ProfileResult(Profile.DEVELOPER, round(confidence, 2), dev_found[:5])

    confidence = min(0.6 + non_dev_score * 0.1, 1.0)
    return ProfileResult(Profile.NON_DEVELOPER, round(confidence, 2), non_dev_found[:5])
