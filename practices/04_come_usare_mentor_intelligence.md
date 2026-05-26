# Guida — Come usare MentorIntelligence

## Cosa fa MentorIntelligence

MentorIntelligence costruisce un percorso di onboarding personalizzato per ogni
nuovo membro del team. Rileva il profilo dell'utente (junior/senior, developer/devops/
analyst), genera un percorso di apprendimento strutturato, e risponde alle domande
attingendo simultaneamente da tre knowledge base: codice, documenti e best practices.

## Quando usarlo

- Nuovo developer entra nel team → avvia una sessione di onboarding
- Membro del team vuole capire un'area del progetto che non conosce
- Manager vuole creare un percorso formativo strutturato per i nuovi assunti

## Pipeline completo

### Step 1 — Prepara le best practices
Crea una cartella `practices/` con file Markdown che descrivono:
- Convenzioni del team
- Guide di onboarding
- Runbook e procedure
- Come usare gli strumenti del progetto

```bash
mi-ingest ./practices           # indicizza le best practices
```

### Step 2 — Avvia il server
```bash
mi-serve                        # porta 8082
```

## Come iniziare una sessione di onboarding

### Via API REST

```bash
# 1. Crea sessione di onboarding
curl -X POST http://localhost:8082/api/v1/mentor/onboard \
  -H "Content-Type: application/json" \
  -d '{
    "user_name": "Marco",
    "role_hint": "backend developer",
    "intro": "Sono un developer Python con 3 anni di esperienza, mi occupo di API REST e database. È il mio primo giorno su questo progetto."
  }'
```

Risposta:
```json
{
  "session_id": "abc123",
  "profile": "senior_developer",
  "welcome_message": "Ciao Marco! Ho rilevato il tuo profilo come senior_developer...",
  "first_step": {"title": "Architettura generale", ...},
  "suggested_first_question": "Come è strutturato il progetto?"
}
```

### Step 3 — Fai domande nel contesto della sessione

```bash
curl -X POST http://localhost:8082/api/v1/mentor/ask \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc123",
    "question": "Come funziona il pipeline di embedding?"
  }'
```

### Step 4 — Controlla il progresso

```bash
curl http://localhost:8082/api/v1/mentor/progress/abc123
```

## Profili rilevati automaticamente

| Profilo | Caratteristiche dell'intro |
|---------|---------------------------|
| `junior_developer` | "sono alle prime armi", "sto imparando", "ho poca esperienza" |
| `senior_developer` | "anni di esperienza", "conosco Python/Java/Go", "ho lavorato su..." |
| `devops_engineer` | "infrastruttura", "kubernetes", "CI/CD", "docker" |
| `data_engineer` | "pipeline", "ETL", "dati", "spark", "airflow" |
| `analyst` | "analisi", "report", "business", "dati" |

## Usare l'API Python

```python
import httpx

BASE = "http://localhost:8082"

# Crea sessione
session = httpx.post(f"{BASE}/api/v1/mentor/onboard", json={
    "user_name": "Vincenzo",
    "intro": "Sono un data engineer senior, primo giorno su IntelligenceSuite."
}).json()

print(f"Profilo: {session['profile']}")
print(f"Messaggio: {session['welcome_message']}")

# Fai domande
answer = httpx.post(f"{BASE}/api/v1/mentor/ask", json={
    "session_id": session["session_id"],
    "question": "Da dove inizio per capire l'architettura?"
}, timeout=120).json()

print(f"Risposta: {answer['answer']}")
print(f"Prossimo step suggerito: {answer['suggested_next']}")
```

## Configurazione consigliata per MentorIntelligence

MentorIntelligence beneficia del modello più capace disponibile — le risposte
di onboarding richiedono ragionamento e chiarezza:

```env
# Opzione A — Claude (massima qualità pedagogica)
MI_LLM_BACKEND=claude
MI_LLM_MODEL=claude-sonnet-4-5

# Opzione B — Ollama locale con modello più grande
MI_LLM_BACKEND=ollama
MI_LLM_MODEL=llama3.2:8b
```

## Best practices per le guide di onboarding

Quando scrivi file `.md` per le practices, strutturali così:
- **Titolo chiaro** con H1
- **Sezioni brevi** (H2/H3) — ogni sezione diventa un chunk separato
- **Esempi concreti** con comandi reali
- **Domande frequenti** dei nuovi arrivati
- **Link a risorse** interne ed esterne

Più le guide sono specifiche e concrete, migliori saranno le risposte di MentorIntelligence.
