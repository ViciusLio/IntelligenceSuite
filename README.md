# IntelligenceSuite

**Recupera conoscenza aziendale in secondi, non in ore.**

Suite modulare di librerie RAG domain-aware per ambienti enterprise on-premise.
Zero cloud obbligatorio. Zero lock-in. Tutto sotto il tuo controllo.

## Il problema che risolve

Quanto tempo perde il tuo team ogni settimana a cercare dove è implementata
una funzione, rileggere una procedura per ricordare un dettaglio, chiedere
ai colleghi cosa fa quel servizio di cui nessuno ha scritto la doc?

IntelligenceSuite indicizza codice e documenti aziendali e risponde in
linguaggio naturale, con citazione precisa della fonte, in locale.

## Componenti

| Libreria              | Dominio              | Status       |
|-----------------------|----------------------|--------------|
| `CodeIntelligence`    | Codice sorgente      | ✅ Stabile   |
| `DocIntelligence`     | Documenti aziendali  | ✅ Sviluppo  |
| `MentorIntelligence`  | Onboarding adattivo  | ✅ Sviluppo  |
| `intelligence_core`   | Layer condiviso      | ✅ Sviluppo  |

## Quickstart — CodeIntelligence

```bash
pip install -e ".[dev]"
cp .env.example .env
python -m CodeIntelligence.parse_repo /path/to/repo
python -m CodeIntelligence.rag_server
curl -X POST http://localhost:8080/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Dove viene gestita l autenticazione?"}'
```

## Quickstart — DocIntelligence

```bash
pip install -e ".[pdf,docx,xlsx]"
python -m DocIntelligence.ingest_docs /path/to/docs
python -m DocIntelligence.doc_server
curl -X POST http://localhost:8080/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Prerequisiti per il deploy in produzione?"}'
```

## Quickstart — MentorIntelligence

```bash
# 1. Installa (richiede CodeIntelligence e DocIntelligence già indicizzati)
pip install -e ".[pdf,docx,xlsx]"

# 2. (Opzionale) Ingesta prassi aziendali
mkdir practices
echo "# Naming convention\n..." > practices/git_convention.md
python -m MentorIntelligence.content.ingest_practices ./practices

# 3. Avvia il server mentor
python -m MentorIntelligence.mentor_server

# 4. Avvia una sessione di onboarding
curl -X POST http://localhost:8080/api/v1/mentor/onboard \
  -H "Content-Type: application/json" \
  -d '{"user_name": "Mario", "intro": "Sono uno sviluppatore Python, primo giorno."}'

# 5. Fai domande nel contesto del tuo percorso
curl -X POST http://localhost:8080/api/v1/mentor/ask \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "question": "Come funziona l autenticazione?"}'
```

## Requisiti hardware

| Scenario                     | Hardware                        |
|------------------------------|---------------------------------|
| Dev / prova locale           | Mac o PC con 16GB RAM           |
| Team 1-10 persone            | Server con 32GB RAM             |
| Team 10-50 persone (GPU)     | RTX 3090/4090 + 64GB RAM        |
| Team 50+ persone             | pgvector + GPU dedicata         |

Leggi [ARCHITECTURE.md](ARCHITECTURE.md) per le decisioni di design.

## License

MIT
