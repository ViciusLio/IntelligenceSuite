# Architecture — Intelligence Suite

## Filosofia di design

**Chunk come testo leggibile.**
Un chunk non è un blob opaco. È testo narrativo che un umano capisce
aprendo il JSONL con qualsiasi editor. Questo rende il sistema debuggabile,
estendibile, e trasparente.

**Locale-first, cloud on-demand.**
Funziona completamente senza internet. L'escalation a Claude API è
un miglioramento opzionale, non un prerequisito. Costo fisso: 0€.

**Zero lock-in.**
Vector store swappabile (ChromaDB → pgvector). LLM swappabile.
Parser pluggable. Il contratto tra componenti è solo il formato JSONL.

**Best-effort sempre.**
Nessun parser crasha su un file che non riesce a leggere.
Degrada a chunk raw se il parsing strutturato fallisce.

**Un file, una responsabilità.**
Max 400 righe per file. Se cresce oltre, sta facendo troppe cose.

## Stack

| Componente    | Default               | Alternativa         |
|---------------|-----------------------|---------------------|
| Vector Store  | ChromaDB embedded     | pgvector (Postgres) |
| LLM locale    | Ollama + qwen2.5      | llama.cpp, LMStudio |
| LLM cloud     | Claude API            | OpenAI API          |
| Embedding     | nomic-embed-text      | voyage-code-2       |
| API Framework | FastAPI               | —                   |
| Scambio dati  | JSONL                 | —                   |

## Schema chunk (contratto universale)

```json
{
  "id":         "domain::type::locator",
  "domain":     "code | doc | api | data | mentor",
  "type":       "function | class | section | table | practice | onboarding_step | ...",
  "text":       "testo human-readable, autocontenuto",
  "source":     "path/relativo/file.ext",
  "language":   "python | pdf | docx | ...",
  "metadata":   {},
  "checksum":   "sha256 del testo",
  "indexed_at": "2026-05-25T10:00:00Z"
}
```

## Architettura MentorIntelligence

```
utente
  │
  ▼
mentor_server.py          ← endpoint HTTP: /onboard /ask /progress /reset
  │
  ├── profile_detector.py ← rileva profilo dall'input iniziale
  ├── path_builder.py     ← costruisce/aggiorna il percorso adattivo
  ├── session_manager.py  ← persiste stato sessione (JSON su disco)
  │
  └── orchestrator.py     ← fonde risposte da:
        ├── CodeIntelligence.Retriever  (chunk domain=code)
        ├── DocIntelligence.Retriever   (chunk domain=doc)
        └── store locale domain=mentor  (prassi, guide, percorsi)
```

## KPI production-ready

| Metrica              | CodeIntelligence | DocIntelligence | MentorIntelligence      |
|----------------------|------------------|-----------------|-------------------------|
| Hit@1                | > 60%            | > 55%           | > 65% (passo giusto)    |
| Hit@5                | > 85%            | > 80%           | > 90% (percorso ok)     |
| MRR                  | > 0.70           | > 0.65          | > 0.75                  |
| Latenza P50 locale   | < 300ms          | < 400ms         | < 500ms                 |
| Latenza P99 locale   | < 1000ms         | < 1200ms        | < 2000ms                |
| Tasso escalation     | < 15%            | < 15%           | < 20%                   |

## Roadmap domini

- ✅ `CodeIntelligence` — codice sorgente
- ✅ `DocIntelligence`  — documenti aziendali
- ✅ `MentorIntelligence` — onboarding adattivo
- 📋 `APIIntelligence`  — spec OpenAPI, Postman
- 📋 `DataIntelligence` — schemi DB, query, pipeline
