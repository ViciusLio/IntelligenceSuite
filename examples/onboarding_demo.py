"""Demo MentorIntelligence — sessione onboarding completa (senza server HTTP)."""

from __future__ import annotations
from pathlib import Path

from MentorIntelligence.profile_detector import detect_profile, Profile
from MentorIntelligence.session_manager import (
    create_session, save_session, mark_step_complete, record_question,
)
from MentorIntelligence.path_builder import build_path, compute_progress, get_current_step


def run_demo():
    print("=" * 60)
    print("MentorIntelligence — Demo Sessione Onboarding")
    print("=" * 60)

    # Rileva profilo
    intro = "Sono uno sviluppatore Python, lavoro su backend da 3 anni, primo giorno in azienda."
    profile_result = detect_profile(intro)
    print(f"\nIntro: {intro}")
    print(f"Profilo rilevato: {profile_result.profile.value} "
          f"(confidenza: {profile_result.confidence:.0%})")
    print(f"Segnali: {profile_result.signals[:3]}")

    # Crea sessione
    session = create_session("Mario", profile_result.profile.value)
    print(f"\nSessione creata: {session.session_id[:8]}...")

    # Costruisce percorso
    path = build_path(session.profile)
    print(f"\nPercorso '{session.profile}': {len(path)} passi")
    for i, step in enumerate(path):
        print(f"  {i + 1}. [{step['id']}] {step['title']}")
        print(f"       Sorgenti: {step['sources']}")
        print(f"       Checkpoint: {step.get('checkpoint', '')}")

    # Simula avanzamento
    print("\n--- Simulazione avanzamento ---")

    current = get_current_step(session)
    print(f"\nPasso corrente: {current['title']}")
    print(f"Domanda suggerita: {current['suggested_queries'][0]}")

    record_question(
        session,
        "Qual è l'architettura del progetto?",
        "IntelligenceSuite è composto da intelligence_core, CodeIntelligence, DocIntelligence e MentorIntelligence.",
        ["doc::section::ARCHITECTURE.md.architettura"],
    )

    mark_step_complete(session, path[0]["id"])
    progress = compute_progress(session)
    print(f"\nProgresso dopo step 1: {progress['completed']}/{progress['total']} "
          f"({progress['percent']}%)")
    print(f"Prossimo step: {progress['next_step_title']}")

    # Salva sessione
    save_session(session)
    print(f"\nSessione salvata in .mentor_sessions/{session.session_id[:8]}....json")

    print("\n" + "=" * 60)
    print("Demo completata. Per la versione server:")
    print("  python -m MentorIntelligence.mentor_server")
    print("  curl -X POST http://localhost:8080/api/v1/mentor/onboard \\")
    print('    -d \'{"user_name": "Mario", "intro": "Sono uno sviluppatore..."}\'')
    print("=" * 60)


if __name__ == "__main__":
    run_demo()
