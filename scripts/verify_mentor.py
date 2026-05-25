"""Verifica end-to-end di MentorIntelligence (Fase 3.5)."""
from MentorIntelligence.profile_detector import detect_profile, Profile
from MentorIntelligence import session_manager, path_builder

# 1. Rileva profilo
r = detect_profile("Sono uno sviluppatore Python, lavoro su microservizi e uso Docker ogni giorno")
print(f"Profilo: {r.profile} | Confidence: {r.confidence:.2f} | Segnali: {r.signals}")

# 2. Crea sessione
s = session_manager.create_session("Mario Rossi", r.profile)
print(f"Sessione: {s.session_id} | Utente: {s.user_name} | Profilo: {s.profile}")

# 3. Costruisci percorso
path = path_builder.build_path(r.profile)
print(f"Step nel percorso: {len(path)}")
for step in path:
    print(f"  - [{step['id']}] {step['title']} (fonti: {step['sources']})")

# 4. Progresso iniziale
progress = path_builder.compute_progress(s)
print(f"Progresso: {progress['completed']}/{progress['total']} ({progress['percent']}%) | Prossimo: {progress['next_step_title']}")

# 5. Completa il primo step e ricalcola
session_manager.mark_step_complete(s, path[0]["id"])
progress2 = path_builder.compute_progress(s)
print(f"Dopo completamento step 1: {progress2['completed']}/{progress2['total']} ({progress2['percent']}%)")

# 6. Registra una domanda
session_manager.record_question(s, "Come si configura il retriever?", "Usa Retriever.load_default()", ["doc", "code"])
print(f"Domande registrate: {len(s.questions_asked)}")

print("\nVerifica MentorIntelligence: OK")
