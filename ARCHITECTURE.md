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
  "domain":     "code | doc | api | data | mentor | qa",
  "type":       "function | class | section | table | practice | onboarding_step | ...",
  "text":       "testo human-readable, autocontenuto",
  "source":     "path/relativo/file.ext",
  "language":   "python | pdf | docx | ...",
  "metadata":   {},
  "checksum":   "sha256 del testo",
  "indexed_at": "2026-05-25T10:00:00Z"
}
```

## Capacità enterprise (multi-progetto, auth, observability)

Tre feature opt-in, tutte con default che riproducono il comportamento
pre-0.9.0 (**zero breaking changes**), implementate con sola stdlib +
FastAPI/Starlette (nessuna nuova dipendenza).

**Multi-progetto (`IS_PROJECT`).**
`intelligence_core/paths.py` è l'unica fonte di verità per i nomi delle
collection ChromaDB e per le directory di stato, risolti a runtime in base a
`IS_PROJECT`:

| | `IS_PROJECT` non impostato (`default`) | `IS_PROJECT=acme` |
|---|---|---|
| Collection | `code_intelligence`, `doc_intelligence`, … | `acme_code_intelligence`, … |
| Stato su disco | `~/.intelligence_suite/<chroma\|graph\|eval\|skill_sessions>/` | `~/.intelligence_suite/acme/<…>/` |

Nessun dato passa da un progetto all'altro: cambiare `IS_PROJECT` e ri-eseguire
l'ingest è sufficiente per isolare client/team/ambienti sulla stessa macchina.

**Autenticazione (`IS_AUTH_ENABLED` / `IS_API_KEY`).**
`intelligence_core/auth.py` è un middleware **ASGI puro** (non
`BaseHTTPMiddleware`) così le risposte SSE non vengono mai bufferizzate. Quando
abilitato, ogni path `/api/v1/*` richiede `Authorization: Bearer <IS_API_KEY>`;
i path pubblici (`/`, `/health`, `/docs`, `/redoc`, `/openapi.json`) restano
aperti. Token mancante/errato → `403 {"error":"invalid_api_key"}`. Se l'auth è
on ma la chiave è vuota, `verify_auth_config()` impedisce l'avvio
(`AuthConfigError`). `auth_headers()` fornisce gli header corretti per le
chiamate inter-modulo (dict vuoto se l'auth è off).

**Observability (`IS_LOG_LEVEL` / `IS_LOG_FORMAT` / `IS_METRICS_ENABLED`).**
`intelligence_core/observability.py` centralizza logging strutturato (un oggetto
JSON per riga su stdout, fallback `text` per il dev) e un `MetricsCollector`
in-memory thread-safe. Un evento `query` per ogni chiamata a `/api/v1/query` e
`/api/v1/stream`, un evento `ingestion` a fine embed. **Mai testo di
domande/risposte nei log** — solo metadati (es. la *lunghezza* della domanda).
`GET /metrics` è opt-in: assente (404) finché `IS_METRICS_ENABLED=true`.

## Ingestione on-demand & Export (superficie runtime)

Due capacità opt-in che affiancano i CLI offline (`*-parse`/`*-ingest` +
`*-embed`) con una superficie HTTP, **senza** sostituirli: stessi parser, stessa
idempotenza via checksum in-store. Default invariati (zero breaking changes).

**Ingestione on-demand (`IS_INGEST_ENABLED` / `IS_INGEST_ROOT` / `IS_INGEST_MAX_MB`).**
`intelligence_core/ingestion.py` è il motore; `intelligence_core/ingest_api.py`
monta le route (assenti → 404 finché `IS_INGEST_ENABLED=true`).

| Route | Funzione |
|---|---|
| `POST /api/v1/ingest/path` | indicizza un path lato server, confinato a `IS_INGEST_ROOT` (disabilitata finché la variabile è vuota) |
| `POST /api/v1/ingest/upload` | indicizza file caricati (richiede l'extra `[ingest]` → `python-multipart`; cap per-file `IS_INGEST_MAX_MB`, default 50 → 413 oltre soglia) |
| `GET /api/v1/ingest/status/{job_id}` | stato del job asincrono |

- **Async**: ogni richiesta torna un `job_id`; una `JobRegistry` thread-safe
  in-memory traccia i job su thread daemon, interrogabili via polling.
- **Idempotente**: re-ingestare contenuto invariato non embedda nulla
  (match checksum); scansioni di path completi fanno pruning degli orfani.
- **Best-effort**: un singolo file illeggibile viene loggato e saltato,
  mai fatale.
- **Sicurezza path**: `path` ingest confinato a `IS_INGEST_ROOT`; upload
  limitato da `IS_INGEST_MAX_MB`.

Moduli esposti: `code`, `doc`, `mentor`, `proposal`.

**Export (`POST /api/v1/export`).**
`intelligence_core/export.py` (renderer) + `intelligence_core/export_api.py`
(route, montata sempre). Documento generico
`{format, title, sections:[{heading, body, sources}]}` riusabile sia dalla chat
(messaggi conversazione) sia da Proposal (Q&A). Risposta come allegato via
`Content-Disposition`.

| Formato | Dipendenza | Errore se assente |
|---|---|---|
| `markdown` | solo stdlib | — |
| `html` | solo stdlib (escaped, standalone) | — |
| `pdf` | extra `[export]` → `fpdf2` | `503` |

Formato sconosciuto → `400`. Solo il PDF degrada (503) quando `[export]` non è
installato; Markdown/HTML sono sempre disponibili.

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

- ✅ `CodeIntelligence`     — codice sorgente
- ✅ `DocIntelligence`      — documenti aziendali
- ✅ `MentorIntelligence`   — onboarding adattivo
- ✅ `SkillIntelligence`    — registry/sessioni di competenze
- ✅ `ProposalIntelligence` — risposte a gare/RFP da knowledge base Q&A
- 🧪 `AgentIntelligence`    — orchestrazione agentica (stub/sperimentale)
- 📋 `APIIntelligence`      — spec OpenAPI, Postman
- 📋 `DataIntelligence`     — schemi DB, query, pipeline
