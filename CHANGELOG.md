# Changelog

All notable changes to IntelligenceSuite are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

---

## [0.14.0] — 2026-06-05

### Added
- **OpenAI-compatible gateway** (`intelligence_gateway/`, `gw-serve`, port 8086) —
  a thin protocol adapter exposing a standard OpenAI API (`GET /v1/models`,
  `POST /v1/chat/completions`, streaming + non-streaming) in front of the module
  servers, so any OpenAI-speaking client (OpenWebUI, LibreChat, the `openai` SDK,
  IDE plugins, `curl`) can use IntelligenceSuite with no bespoke integration. It
  holds no retrieval logic — it translates OpenAI ↔ IntelligenceSuite and proxies
  over HTTP, forwarding the caller's `Authorization` header upstream. Exposes five
  models — `code-/doc-/mentor-/proposal-intelligence` plus an `intelligence-suite`
  auto-router (keyword heuristic) — and returns the answering module in the
  `X-IS-Module` response header. New settings `GW_PORT` (default 8086) and
  `GW_UPSTREAM_HOST` (default `localhost`, set to a service name under
  docker-compose). README gains an *OpenAI-compatible gateway* section with the
  OpenWebUI configuration guide.
- **ProposalIntelligence now speaks the standard single-question contract** —
  `POST /api/v1/query` and `POST /api/v1/stream` (SSE), the same surface the other
  modules expose via `server_base`. Both reuse Proposal's own few-shot style
  pipeline (mode-specific system prompt + temperature, Q&A example retrieval), so
  answers are identical to the batch path — only the delivery changes. The stream
  endpoint emits real `token` events as the LLM generates (first token in ~0.8s
  instead of waiting for the whole answer), bridged from the provider's sync
  `stream()` via a background thread, with a `generate()` fallback for providers
  without streaming (e.g. Claude). This lets the gateway drive **all five** models
  through one uniform path — no per-module branching — so selecting
  `proposal-intelligence` in OpenWebUI streams token-by-token like the others
  instead of returning 404. The existing `POST /api/v1/proposal/answer` batch
  endpoint is unchanged and stays for the questionnaire workflow.
  (`ProposalIntelligence/proposal_server.py`)

---

## [0.13.1] — 2026-06-04

### Fixed
- **`ESCALATION_THRESHOLD` / `ESCALATION_MAX_TOKENS` were silently ignored** — the
  RAG server constructed `EscalationPolicy()` with no arguments, and the policy
  read its threshold from `os.getenv(...)`. pydantic-settings loads `.env` into
  the `settings` object but does **not** inject those values into `os.environ`,
  so `os.getenv("ESCALATION_THRESHOLD")` never saw the `.env` value and the
  threshold stayed at the hardcoded `0.70` (the `escalation_threshold` settings
  field was effectively dead). Effect: with an `ANTHROPIC_API_KEY` set, every
  answer whose retrieval confidence was < 0.70 escalated to Claude regardless of
  the configured `.env` value. `create_app` now passes
  `settings.escalation_threshold` and `settings.escalation_max_tokens` into the
  policy, so the documented `.env` knobs actually take effect.
  (`intelligence_core/server_base.py`)

### Added
- **`embed_backend` + `embed_model` in `/health`** — both the shared RAG server
  (`intelligence_core/server_base.py`) and the Proposal server now report the
  embedder the running process uses. This makes a query-vs-index model drift
  visible (e.g. a server started before `ST_MODEL` changed embeds queries with a
  different model than the stored vectors → near-zero similarity → "No relevant
  documents found"). Embedders expose a uniform `model_name`; the field is read
  without probing the backend over the network. Additive `/health` keys.

---

## [0.13.0] — 2026-06-04

### Added
- **Export** (SOTTO-FASE D) — `POST /api/v1/export` on every module server (and
  the Proposal server) turns a client-supplied document (a title + sections, e.g.
  a chat conversation or a set of Proposal answers) into a downloadable file.
  - `intelligence_core/export.py` — renderers for **Markdown** and a standalone
    **HTML** page (stdlib, always available) and **PDF** (via `fpdf2`).
  - `intelligence_core/export_api.py` — the route; returns the file as an
    attachment with the right `Content-Type` / `Content-Disposition`. Unknown
    format → 400; `format=pdf` without the extra → 503 (Markdown/HTML keep working).
  - **`[export]` optional extra** (`pyproject.toml`): `fpdf2` — enables PDF output
    without adding a hard dependency. Also folded `ingest` + `export` into `[all]`.
  - **UI**: a "⬇︎ Esporta" menu (Markdown / HTML / PDF) in the chat top bar
    (exports the active conversation) and in the Proposal header (exports the
    generated answers, shown once answers exist).
  - **Tests**: `tests/test_export_api.py` — renderers, PDF magic-bytes + the
    dependency-missing 503 branch, and the HTTP route per format (10 tests).
- **Ingest UI** (SOTTO-FASE C) — a "📥 Indicizza contenuti" panel in the chat UI
  (`intelligence_ui/templates.py`, shared by Code/Doc/Mentor) and in the
  ProposalIntelligence single-page UI (`ProposalIntelligence/web.py`). The panel
  is shown **only when** the server reports ingest is enabled.
  - Code → server-side path field (`POST /api/v1/ingest/path`, confined to
    `IS_INGEST_ROOT`); Doc/Mentor/Proposal → file upload
    (`POST /api/v1/ingest/upload`).
  - After submit the UI polls `GET /api/v1/ingest/status/{job_id}` and shows a
    live status (queued → running → done/error) with new/skipped/deleted counts,
    then refreshes the indexed-chunk count.
- **`ingest_enabled` in `/health`** — both the shared RAG server
  (`intelligence_core/server_base.py`) and the Proposal server now expose
  `ingest_enabled` so the browser can gate the ingest panel. Additive field;
  existing keys unchanged.
- **Tests**: `tests/test_ingest_ui.py` — `/health` exposes `ingest_enabled`
  (RAG + Proposal, on/off) and both HTML templates carry the ingest-panel markers
  (5 tests, offline).

### Docs
- **README restructured** — clickable table of contents, trimmed non-representative
  content, updated ingest Mermaid (CLI + on-demand API entry points) and a new
  "Operational surface — ingest & export" diagram.
- **ARCHITECTURE.md** — documents the on-demand ingestion & export runtime surface,
  aligns the domain roadmap with the modules that now exist, adds the `qa` domain.

### Notes
- **Zero breaking changes**: the panel is hidden unless `IS_INGEST_ENABLED=true`,
  and `ingest_enabled` is a purely additive `/health` field.

---

## [0.12.0] — 2026-06-04

### Added
- **Ingest HTTP API** (`intelligence_core/ingest_api.py`) — opt-in routes mounted
  on every module server (and the Proposal server) **only when**
  `IS_INGEST_ENABLED=true`; otherwise absent (404), behavior identical to
  v0.11.x. All routes sit behind the existing Bearer auth middleware.
  - `POST /api/v1/ingest/path` — index a server-side path (validated inside
    `IS_INGEST_ROOT`). Returns `{job_id, status}` and runs parse+embed in a
    background thread.
  - `POST /api/v1/ingest/upload` — index uploaded files (multipart). Per-file cap
    `IS_INGEST_MAX_MB` (413 on overflow); files are saved to a temp dir, ingested,
    then cleaned up. Requires the new `[ingest]` extra (`python-multipart`); if
    that extra is absent the route is simply not mounted (path + status still work).
  - `GET /api/v1/ingest/status/{job_id}` — poll job status/stats (404 if unknown).
  - Each request targets the hosting server's module by default; an optional
    `module` field can retarget to any of `code | doc | mentor | proposal`.
- **`[ingest]` optional extra** (`pyproject.toml`): `python-multipart` — enables
  the upload endpoint without making it a hard dependency.
- **Tests**: `tests/test_ingest_api.py` — opt-in gate, path validation
  (outside-root / unknown-module / empty-root → 4xx), async job hand-off + status
  polling, upload happy-path, and oversize rejection (9 tests, offline).

### Notes
- **Zero breaking changes**: no routes exist unless `IS_INGEST_ENABLED=true`.
  The heavy parse+embed always runs asynchronously, so the HTTP call returns at
  once with a `job_id` to poll.

---

## [0.11.0] — 2026-06-04

### Added
- **On-demand ingestion service** (`intelligence_core/ingestion.py`) — the engine
  behind the upcoming ingest API/UI. Parses + embeds either a server-side path or
  a set of uploaded files for any of the four modules (`code`, `doc`, `mentor`,
  `proposal`), reusing each module's **existing parsers** and the **in-store
  checksum idempotency** (only new/changed chunks are embedded; unchanged content
  is skipped). Highlights:
  - **Best-effort**: a single unreadable file is logged and skipped, never fatal.
  - **Async jobs**: thread-safe `JobRegistry` / `IngestJob` (`queued → running →
    done | error`); `submit()` returns a `job_id` to poll. Mirrors the
    observability `MetricsCollector` pattern.
  - **Path safety**: `validate_path()` confines server-side path ingest to
    `IS_INGEST_ROOT` (defence against path traversal) and is **disabled entirely**
    until that variable is set.
  - **Orphan pruning** only on full-directory path scans; uploads (partial sets)
    never prune.
- **CSV/TSV parser** (`DocIntelligence/parsers/csv_parser.py`, stdlib-only) —
  produces a schema *section* chunk + a preview *table* chunk; registered in the
  Doc parser registry. No new dependency.
- **Config** (all opt-in, default = current behavior): `IS_INGEST_ENABLED`
  (default `false`), `IS_INGEST_ROOT` (default empty → path ingest off until set),
  `IS_INGEST_MAX_MB` (default `50`).
- **Tests**: `tests/test_ingestion.py` — CSV parsing, upload-mode ingest,
  idempotency, per-module dispatch (doc/mentor/proposal), `IS_INGEST_ROOT` path
  safety, orphan pruning, and the async job registry (18 tests, fully offline).

### Notes
- **Zero breaking changes**: no HTTP routes are added in this release — the
  service is library-only. API endpoints and UI panels land in later releases,
  also gated behind `IS_INGEST_ENABLED`.

---

## [0.10.0] — 2026-06-04

### Added
- **Deterministic KPI tests in CI** — retrieval quality is now verified on every
  commit instead of being skipped when no live index exists:
  - Versioned **synthetic fixtures** in `tests/fixtures/` (`kpi_code_chunks.json`,
    `kpi_doc_chunks.json`, `kpi_qa.json`) — realistic but non-confidential.
  - `tests/conftest.py`: a dependency-free `HashingEmbedder` (bag-of-words →
    cosine similarity = lexical overlap) plus fixtures that mount a **disk-less,
    in-memory ChromaDB** and return a ready `Retriever`. Collection naming reuses
    the Fase-1 `paths.collection_name(...)` (classic names for the default
    project). No Ollama, no network, no optional extra, no disk.
  - `tests/test_kpi.py`: Hit@1 / Hit@5 / MRR on known chunks, confidence always
    in `[0,1]`, sequential ranks, generous CI latency ceiling. These **fail for
    real** if the retriever is broken.
- **pytest markers** (`pyproject.toml`): `kpi` (retrieval quality on in-memory
  store — runs in CI, never skips) and `slow` (needs a real embedding backend /
  network — exclude with `pytest -m "not slow"`).
- **`CI.md`** at the repo root — how to run the full suite, exclude slow tests,
  run only the KPI tests, and why `ci-eval` stays out of standard CI.

### Changed
- `intelligence_core/store.py`: `ChromaStore` accepts `persist_dir=":memory:"` to
  use an ephemeral, disk-less client (used by the KPI fixtures). Any other value
  persists exactly as before — zero behaviour change for existing callers.
- `README.md`: "Test suite" section documents the markers and the in-memory KPI
  tests.

---

## [0.9.2] — 2026-06-04

### Added
- **Structured observability** — new module `intelligence_core/observability.py`
  (stdlib only, no new dependency):
  - Centralized logger emitting **one JSON object per line to stdout** by default
    (`IS_LOG_FORMAT=json`), with a human-readable `text` fallback for local dev.
    Level via `IS_LOG_LEVEL` (default `INFO`).
  - One structured `query` event per call to `/api/v1/query`, with metadata only:
    module, project, intent, question length, top_k, confidence, escalated,
    backend, latency_ms. **Question/answer text is never logged.**
  - One structured `ingestion` event at the end of each embed run (`ci-embed`,
    `di-embed`, `pi-embed`): total / new / skipped chunks, duration, backend.
  - In-memory, thread-safe `MetricsCollector` (counters reset on restart).
- **Opt-in `GET /metrics` endpoint** via `IS_METRICS_ENABLED` (default `false`):
  when disabled the route does not exist (404); when enabled it returns
  in-memory counters as JSON (queries total/escalated, avg latency, avg
  confidence, uptime). Registered on all six servers.
- `IS_LOG_LEVEL`, `IS_LOG_FORMAT`, `IS_METRICS_ENABLED` settings — all defaults
  preserve v0.9.1 behaviour (zero breaking changes).

### Changed
- `intelligence_core/server_base.py`: `/api/v1/query` **and** `/api/v1/stream`
  emit a structured event + update metrics on every response path (RAG, agent,
  skill — best-effort, never breaks a request). Streaming events fire once the
  SSE response is fully generated so streamed queries are counted in `/metrics`.
- `CodeIntelligence/embed_chunks.py`, `DocIntelligence/embed_docs.py`,
  `ProposalIntelligence/embed_qa.py`: emit an ingestion event when done.
- `.env.example`: documents `IS_LOG_LEVEL`, `IS_LOG_FORMAT`, `IS_METRICS_ENABLED`.

---

## [0.9.1] — 2026-06-04

### Added
- **API Bearer-token authentication** (`IS_AUTH_ENABLED` / `IS_API_KEY`): when
  `IS_AUTH_ENABLED=true`, all `/api/v1/*` endpoints require the header
  `Authorization: Bearer <IS_API_KEY>`.  `/health` and `/` remain public.
  Returns `{"error":"invalid_api_key"}` with HTTP 403 on missing/wrong token.
- New module `intelligence_core/auth.py` — pure ASGI middleware (no response
  buffering, SSE streaming unaffected) + `add_auth_middleware()` helper +
  `verify_auth_config()` (refuses to start with `AuthConfigError` when auth is
  enabled but `IS_API_KEY` is empty) + `auth_headers()` (returns the right
  `Authorization` header for inter-module calls, empty dict when auth is off).
- `IS_AUTH_ENABLED=false` default → zero breaking changes vs v0.9.0.

### Changed
- `intelligence_core/server_base.py`, `SkillIntelligence/skill_server.py`,
  `AgentIntelligence/agent_server.py`, `ProposalIntelligence/proposal_server.py`:
  all call `add_auth_middleware()` and `warn_if_key_missing()` at startup.
- `.env.example`: documents the new `IS_AUTH_ENABLED` and `IS_API_KEY` variables.

---

## [0.9.0] — 2026-06-04

### Added
- **Multi-project namespacing** (`IS_PROJECT` env var): set `IS_PROJECT=acme` to
  isolate all ChromaDB collections (`acme_code_intelligence`, …) and state
  directories (`~/.intelligence_suite/acme/chroma|graph|eval|skill_sessions/`)
  per project.  Default value `"default"` replicates the exact v0.8.x layout
  with zero breaking changes.
- New module `intelligence_core/paths.py` — single source of truth for
  collection names and state-directory paths, project-aware at call time.

### Changed
- `intelligence_core/graph/store.py`: `GRAPH_DIR` is now a patchable sentinel
  (`None`) resolved at call time via `paths.graph_dir()`.
- `intelligence_core/evaluation/report.py`: same pattern for `EVAL_DIR`.
- `intelligence_core/evaluation/paths.py`: `get_collection()` and
  `get_all_collections()` delegate to `paths.collection_name()` — collection
  names are now project-prefixed when IS_PROJECT is set.
- `intelligence_core/retriever.py`: `Retriever.load_default()` and
  `MultiRetriever.load_default()` pass `persist_dir` from `paths.chroma_dir()`.
- All server and embed entry-points use `paths.collection_name()` at build time;
  `SkillIntelligence` and `AgentIntelligence` resolve collection names at call time.
- Launcher header shows project name when `IS_PROJECT != "default"`.
- `.env.example`: documents the new `IS_PROJECT` variable.

---

## [0.8.1] — 2026-06-03

### Added
- **Web UI per `pi-serve`** (`GET /`): pagina single-page per incollare un
  questionario, scegliere la modalità (anchored/commercial) e il numero di
  esempi di stile, e vedere le risposte generate con le relative fonti.
- **ProposalIntelligence nel launcher**: nuova card (porta 8085) con polling
  `/health` e pulsante "Apri →" verso la web UI.

### Changed
- Launcher: rimossa la card *Agent Intelligence* (era un motore usato dalle chat
  CI·DI·MI, senza una pagina propria da aprire). Rimosso anche il toggle
  "thinking mode" associato. Il modulo e `ai-serve` restano invariati.

---

## [0.8.0] — 2026-06-03

### Added
- **Nuovo modulo `ProposalIntelligence`** — auto-risposta a questionari/gare nel
  proprio *stile aziendale*, ancorata a un corpus di Q&A passate. Pipeline:
  - `pi-ingest` — parsing di corpus strutturati (tabella Markdown/CSV/Excel a 2
    colonne, marcatori `D:`/`R:` · `Q:`/`A:` · `Domanda:`/`Risposta:`) in chunk
    `qa::qa_pair::<hash>` deterministici e idempotenti.
  - `pi-embed` — indicizza in ChromaDB embeddando **la domanda** (non l'intera
    coppia), così una nuova domanda — anche se formulata diversamente — matcha
    le domande passate simili; il chunk recuperato resta la coppia completa per
    il few-shot.
  - `pi-answer` — recupera le coppie più simili come esempi di stile e genera le
    risposte. Due **modalità** selezionabili: `anchored` (fedele al corpus,
    temperatura bassa) e `commercial` (più assertiva/promozionale).
  - `pi-serve` — API REST (`/health`, `POST /api/v1/proposal/answer`) sulla
    porta `8085`.
  - Output in Markdown con fonti di stile e relativi punteggi.
- **Override embedder per-modulo** (`get_module_embedder`): ogni modulo può usare
  un embedder dedicato via `{PREFIX}_EMBED_BACKEND` / `{PREFIX}_EMBED_MODEL`
  (es. `PI_EMBED_*` per un modello multilingue IT/EN) senza re-indicizzare le
  collezioni esistenti.
- Dominio `qa` e tipo `qa_pair` aggiunti allo schema chunk condiviso.
- Dati demo **sintetici** in `examples/proposal/` (corpus + questionario).

### Changed
- README: nuova sezione architetturale "How it works" con diagrammi Mermaid in
  testa, e sezione dedicata a ProposalIntelligence.

---

## [0.7.5] — 2026-06-03

### Added
- `ci-eval --samples N` ora **tronca il testset cachato** a N domande senza
  rigenerare (zero chiamate LLM). Per averne più di quante ce ne sono in cache
  serve `--regenerate`. Utile per A/B rapidi (es. confronto reranker ON/OFF).

### Changed
- `RERANK_CANDIDATES` default `20` → `30`: il cross-encoder riceve più candidati
  da riordinare. Misurato su un A/B (stesso testset): il reranking porta
  `context_precision` +0.14 e `context_recall` +0.15.
- `ci-eval` ora stampa **il numero reale** di domande in valutazione
  (`Domande effettive in valutazione: N`), oltre ai campioni richiesti — prima
  mostrava sempre il default di `--samples` anche quando la cache era più piccola.

---

## [0.7.4] — 2026-06-03

### Added
- **Eval integrato `ci-eval --domain all`**: valuta il sistema su *tutte* le
  collection insieme (code + doc + mentor). Il testset è generato unendo
  `chunks.jsonl` + `doc_chunks.jsonl` + `mentor_chunks.jsonl`, e il retrieval usa
  il nuovo `MultiRetriever` che raccoglie i candidati da ogni collection, li fonde
  e applica **un solo rerank globale** prima del taglio a `top_k`.
- `intelligence_core/retriever.py`: classe `MultiRetriever` (+ `load_default`),
  resiliente a collection vuote/assenti (uno store rotto non blocca gli altri).
- `intelligence_core/evaluation/paths.py`: `BASE_DOMAINS`, `get_all_chunk_paths`,
  `get_all_collections`.

---

## [0.7.3] — 2026-06-03

### Added
- **Cross-encoder reranking** (`intelligence_core/reranker.py`): riordina i
  candidati con un cross-encoder prima del taglio a `top_k`. Leva principale per
  `context_precision`. Opt-in, non-breaking:
  - `RERANK_ENABLED` (default `false`) — attiva il reranking
  - `RERANK_MODEL` (default `cross-encoder/ms-marco-MiniLM-L-6-v2`)
  - `RERANK_CANDIDATES` (default 20) — ampiezza del pool prima del rerank
  - Richiede l'extra `[st]`; se il modello non è disponibile si ricade in modo
    controllato sul keyword-boost legacy.

### Changed
- `Retriever.search`: con reranking attivo allarga il pool di candidati
  (`max(top_k*2, RERANK_CANDIDATES)`); altrimenti comportamento invariato. Il
  keyword-boost legacy è estratto in `_keyword_rerank` (fallback).
- `pyproject.toml` versione `0.7.2` → `0.7.3`.

---

## [0.7.2] — 2026-06-03

### Added
- `ci-eval` stampa un messaggio di avvio (con `flush`) prima degli import pesanti
  di RAGAS/LangChain, così il comando non sembra bloccato durante il cold import
  (~20-60s al primo avvio).

### Fixed
- **`ci-eval` crashava a fine evaluation** con `KeyError: 0`: `_to_scores_dict`
  faceva `dict(scores)` sull'`EvaluationResult` di RAGAS 0.2, che viene iterato
  per indice intero. L'`except` ora cattura anche `KeyError` e usa il fallback
  robusto su `to_pandas()`, che calcola la media per metrica ignorando i NaN dei
  sample finiti in `TimeoutError`.

### Security
- `.gitignore`: aggiunto `tests/eval/*.jsonl`. I testset RAGAS sono generati dal
  corpus indicizzato e possono contenere contenuto riservato — esclusi dal repo.

---

## [0.7.1] — 2026-06-03

### Added
- `THINKING_MODE` tri-stato (`unset` / `true` / `false`): oltre ad attivare il
  chain-of-thought ora può **disattivarlo** esplicitamente sui modelli thinking
  (Qwen3, DeepSeek-R1…). Il flag viene emesso per vLLM (`enable_thinking`) e
  Ollama (`think` nativo) su tutti i path: `generate`, `stream`, `generate_with_tools`.
- `ci-eval --max-docs` (default 150) per limitare il corpus passato al knowledge
  graph RAGAS.

### Fixed
- **`ci-eval` si piantava** su corpus grandi: `generate_testset` passava l'intero
  corpus (1500+ chunk) a RAGAS, e `find_indirect_clusters` (DFS ricorsiva) esplode
  su grafi grandi/densi. Ora il corpus è limitato (`--max-docs`) e i chunk troppo
  corti per ottenere un summary vengono scartati.

### Changed
- README riscritto: solo le funzionalità della 0.7.x, inglese uniforme, rimossi i
  walkthrough Jupyter e gli esempi duplicati, roadmap/vector-store stantii corretti.
- `pyproject.toml` versione `0.7.0` → `0.7.1`.

---

## [0.7.0] — 2026-06-03

### Added
- **RAGAS Evaluation** (v0.5.x line)
  - `intelligence_core/evaluation/` — pipeline completa (generator, runner, evaluator, report)
  - CLI `ci-eval --domain --samples --regenerate --top-k`
  - KPI target: faithfulness ≥ 0.75, answer_relevancy ≥ 0.75,
    context_precision ≥ 0.70, context_recall ≥ 0.68
  - Report storico su disco con delta vs valutazione precedente
  - Dipendenza opzionale `[eval]` (ragas 0.2.x + langchain 0.3 pinnati) — zero impatto sul core
- **Graph delle Dipendenze con NetworkX** (v0.6.x line)
  - `intelligence_core/graph/` — builder (chunk JSONL → DiGraph), store (persistenza JSON),
    retriever (who_calls, impact_analysis, dependencies_of, most_connected, expand_context)
  - **GraphRAG** — espansione contestuale del retriever via grafo non orientato (callers + callees),
    opzionale e non breaking: se il grafo non esiste o fallisce, il retrieval prosegue invariato
  - Nuovo tool agente `analyze_impact` in `AgentIntelligence/tools.py`
  - CLI `ci-graph --stats --top-critical`
  - Metadati `calls`/`imports`/`bases`/`name` aggiunti al parser Python (additivo, AST invariato)
  - Dipendenza opzionale `[graph]` (networkx)
- **Tree-sitter Parser Multilanguage** (v0.7.0)
  - `intelligence_core/parsers/` — `BaseParser`, `TreeSitterParser` e parser TypeScript, Go,
    Java, Rust con parsing strutturale preciso (nomi funzione + chiamate estratte dall'AST)
  - Adapter `CodeIntelligence/parsers/treesitter_adapter.py` — integra i parser class-based nel
    registry modulare riemettendo i chunk in schema unificato; ha la precedenza su TS/Go regex
    e aggiunge Java/Rust. Fallback automatico ai parser regex se `[multilang]` non è installato
  - Parser Python AST invariato
  - Dipendenza opzionale `[multilang]` (tree-sitter + tree-sitter-language-pack)

### Changed
- `pyproject.toml` versione `0.5.0` → `0.7.0`; nuovi extra `[eval]`, `[graph]`, `[multilang]`;
  nuovi entry point `ci-eval`, `ci-graph`

### Tests
- Suite: **257 passed, 5 skipped** (baseline 0.5.0 invariata, zero regressioni)
- Nuovi test: `tests/test_ragas_evaluation.py`, `tests/test_graph.py`,
  `tests/test_treesitter_parsers.py`
- Coverage parser Tree-sitter: 93% su `intelligence_core/parsers`

---

## [0.5.0] — 2026-05-27

### Added
- **Real AgentIntelligence** — replaces the v0.4.0 stub with a full multi-hop ReAct agent
  - `AgentIntelligence/agent.py` — ReAct loop: Reason → Act (tool call) → Observe → repeat
    - Up to `AGENT_MAX_ITERATIONS` iterations (default 5, configurable via `.env`)
    - Final answer forced via `llm.generate()` if max iterations reached
    - Graceful fallback to plain `generate()` if backend has no tool-calling support (e.g. Ollama)
  - `AgentIntelligence/tools.py` — three retrieval tools in OpenAI function-calling schema:
    - `search_code` → CodeIntelligence collection (`code_intelligence`)
    - `search_docs` → DocIntelligence collection (`doc_intelligence`)
    - `search_practices` → MentorIntelligence collection (`mentor_intelligence`)
    - Lazy retriever cache per collection; graceful fallback if collection unavailable
  - `AgentIntelligence/agent_server.py` — real FastAPI server on port 8084
    - `GET /health` — `{status: ok, module: agent, version: 0.5.0, thinking_mode, supports_tools, max_iterations}`
    - `POST /api/v1/query` — runs the ReAct agent, returns `AgentQueryResponse` with `answer`, `intent`, `iterations`, `reasoning`, `tools_used`, `latency_ms`
    - `GET /api/v1/thinking` — returns current thinking mode state
    - `POST /api/v1/thinking` — runtime toggle (persists in-memory while server is up)
- **Qwen3 Thinking Mode** — `THINKING_MODE=true` in `.env` enables chain-of-thought reasoning
  - `intelligence_core/llm/openai_compat.py` — `generate_with_tools()` method added to `OpenAICompatProvider`
    - Passes `extra_body={"chat_template_kwargs": {"enable_thinking": True}}` to vLLM when `thinking=True`
    - Returns raw `ChatCompletionMessage` with `.tool_calls` and `.content`
  - `generate()` also supports thinking mode for RAG answers when `THINKING_MODE=true`
  - `thinking_mode: bool = False` and `agent_max_iterations: int = 5` added to `intelligence_core/config.py`
- **Agent routing wired into all modules** — when `INTENT_AGENT_ENABLED=true`, AGENT-classified queries are routed to AgentIntelligence instead of falling back to RAG
  - Both `/api/v1/query` and `/api/v1/stream` endpoints forward to `run_agent()`
  - Exception during agent run → falls through to RAG (zero downtime)
- **Launcher Agent card** — 4-column grid (was 3) with Agent Intelligence card
  - Live status dot (checks `GET :8084/health`)
  - "Thinking mode" ON/OFF toggle (calls `POST :8084/api/v1/thinking`)
  - "API Docs →" button opens `http://localhost:8084/docs`
- **`/api/v1/stream` intent routing** — chat UI queries now also go through intent classification (SKILL and AGENT paths), previously only `/api/v1/query` was routed

### Changed
- `AgentIntelligence/agent_stub.py` — now delegates to `agent_server.py` (kept for backward compat)
- `ai-serve` CLI entry point now starts the real agent server (was stub in v0.4.0)
- `pyproject.toml` version bumped `0.4.0` → `0.5.0`

---

## [0.4.0] — 2026-05-27

### Added
- **Intent Routing** — transparent RAG / Skill / Agent classifier on all four modules
  - `intelligence_core/intent.py` — two-stage classifier:
    - Stage 1: zero-latency heuristic (keyword triggers, skill-name match, structural rules)
    - Stage 2: minimal LLM call only for ambiguous cases (confidence < 0.85)
    - `IntentLevel` (RAG | SKILL | AGENT), `IntentResult` dataclass
  - `match_skill()` — keyword-based skill matcher (name match → 0.95, description keywords → 0.70–0.85)
  - `extract_parameters()` — extracts required skill parameters from natural language via LLM
  - Automatic fallback to RAG on any LLM failure, bad JSON, or timeout — never crashes
  - `INTENT_ROUTING=false` in `.env` to disable routing; zero overhead when disabled
  - `INTENT_AGENT_ENABLED=false` (default) — AGENT queries fall back to RAG until v0.5.0
- **AgentIntelligence stub** — `AgentIntelligence/` package with stub server on port 8084
  - `GET /health` → `{"status": "stub", "module": "agent"}` — launcher-ready
  - Planned for full implementation in v0.5.0
- **`/api/v1/query` on all modules** — now classifies intent before answering:
  - RAG path: identical behavior to v0.3.x (backward compatible)
  - SKILL path: starts a SkillSession and returns the first step as a natural-language answer
  - Missing parameters: asks the user in natural language instead of returning an error
- **`/api/v1/skill/next`** on all modules (CI, DI, MI) — delegates to `SkillExecutor.next_step()`
- **`QueryResponse`** extended with optional fields: `intent`, `session_id`, `is_last_step`
  (all default to safe values — no breaking change for existing clients)
- Launcher updated with 5th card for AgentIntelligence (coming soon, gray dot, port 8084)
- `ai-serve` CLI entry point — starts AgentIntelligence stub on port 8084
- `agent_port: int = 8084`, `intent_routing: bool = True`, `intent_confidence_threshold: float = 0.85`,
  `intent_agent_enabled: bool = False` added to `intelligence_core/config.py`

### Tests
- 58 new tests in `tests/test_intent_routing.py`: heuristic classifier, skill matcher, parameter
  extraction, fallback behaviour, full routing integration, server endpoints (parametrized ×4),
  `QueryResponse` schema, config fields
- Coverage on `intelligence_core/intent.py`: **97%**
- Zero regressions on the 101 tests from v0.3.0

### Changed
- `/api/v1/query` on all modules now classifies intent before responding
  (backward compatible — same request/response signature, new fields are optional)
- `SkillIntelligence` server now exposes `/api/v1/query` and unified `/api/v1/skill/next`
  alongside the existing `/api/v1/skill/start` and `/api/v1/skill/session/{id}`
- Launcher grid expanded to 5 columns

---

## [0.3.0] — 2026-05-27

### Added
- **SkillIntelligence** — new module providing step-by-step procedural guidance with
  cross-domain RAG (code + doc + mentor):
  - `BaseSkill` / `SkillStep` / `SkillContext` / `SkillResult` — Python dataclass interface
    for skill definitions; skills can be defined in pure Python or Markdown
  - `SkillRegistry` — auto-discovers Python skills (`SkillIntelligence/skills/`) and
    Markdown skills (`skill_docs/`); Python definitions win on duplicate name
  - `SkillParser` — rule-based Markdown → Skill parser (zero LLM dependency); supports
    `**Domini:**`, `**Query:**` and `{param}` interpolation in knowledge query templates
  - `SkillExecutor` — session management with JSON persistence
    (`~/.intelligence_suite/skill_sessions/`), cross-domain retrieval, LLM guidance generation;
    all dependencies injectable for zero-disk unit testing
  - `skill_server.py` — FastAPI REST API on port `SI_PORT` (default 8083):
    `GET /health`, `GET /api/v1/skill/list`, `POST /api/v1/skill/start`,
    `POST /api/v1/skill/next`, `GET /api/v1/skill/session/{id}`
  - Two bundled Python skills: `DeployChecklist` (4 steps, code + doc domains) and
    `OnboardingDeveloper` (3 steps, code + doc + mentor domains)
  - Two example Markdown skills: `skill_docs/example_deploy.md` and
    `skill_docs/example_onboarding.md` — ready-to-customise templates
  - CLI entry points: `si-serve` (start the REST API server) and
    `si-ingest <dir>` (load / list Markdown skills from a directory)
  - Launcher dashboard updated with a 4th card for SkillIntelligence (lime colour, port 8083)
  - `si_port: int = 8083` added to `intelligence_core/config.py`

### Tests
- 38 new tests in `tests/test_skill_intelligence.py` (BaseSkill, Parser, Registry, Executor,
  Integration, Server endpoints) — all 38 pass; baseline 63 passed / 5 skipped unchanged;
  grand total **101 passed, 5 skipped**

---

## [0.2.19] — 2026-05-26

### Changed
- Launcher (`is-launch`) rewritten as a pure **navigation hub** — no subprocess management,
  no Start/Stop buttons. Serves a single-page dashboard that polls each module's `/health`
  directly from the browser; shows status dot + chunk count + `Apri →` link per module.
  Zero JS complexity, cannot break.
- `TestKPIThresholds` now auto-skips (instead of failing) when benchmark chunk IDs are not
  found in the indexed store — the tests only run against the reference dataset.
  Test result: **54 passed, 5 skipped, 0 failed**.

---

## [0.2.18] — 2026-05-26

### Added
- **Conversation memory** — the chat now understands follow-up questions:
  - Frontend sends the last 6 messages of the current conversation with every request
  - Backend rewrites short/ambiguous queries into standalone search queries using the LLM
    (e.g. "qualcosa di più in dettaglio?" → "spiegami in dettaglio il Server RAG di DocIntelligence")
  - Conversation history is prepended to the retrieval context so the LLM can reference
    previous turns when generating the answer
  - Heuristic: queries ≤ 7 words or containing follow-up signals (pronouns, "di più",
    "approfondisci", "perché", etc.) trigger rewriting; long self-contained queries skip it

### Changed
- `is-launch` CLI entry point removed from `pyproject.toml` — use `ci-serve` / `di-serve` /
  `mi-serve` directly. The `launcher.py` file is kept but not advertised.

---

## [0.2.17] — 2026-05-26

### Fixed
- Launcher `GET /api/status` was synchronous (`httpx.get` blocking in thread pool).
  Under load or on Ctrl+C, FastAPI cancelled the blocked thread → `CancelledError` /
  `Exception in ASGI application` in the console. Rewritten as a proper `async` endpoint
  using `httpx.AsyncClient` with `asyncio.gather` — all three `/health` checks now run
  in parallel, making status polling ~3× faster and fully non-blocking.

---

## [0.2.16] — 2026-05-26

### Fixed
- Launcher JS completely rewritten back to the v0.2.8 static-HTML approach:
  - **Static buttons** in each card — `Open →` (`<a href>`, always works) and `Start/Stop`
    (single `<button id="btn-{key}">` toggled by poll)
  - **`toggle(key)`** — fire-and-forget POST, shows `⏳ Avvio…` while waiting for the
    API response only, then re-enables and calls `poll()` once. No blocking loop.
  - **`poll()`** — updates dot, label, chunks and button text/class via constants
    (no regex, no innerHTML replacement). Skips disabled buttons to avoid mid-action flicker.
  - **`startAll()`** — single POST to `/api/start-all`, then `poll()`
  - Removed all `window.open` / `_launching` / dynamic `renderActions` complexity

---

## [0.2.15] — 2026-05-26

### Fixed
- Launcher UX reverted to reliable **Start + Apri →** split per card (offline state).
  `window.open()` inside `setInterval` (the poll loop) is silently blocked by browser
  popup blockers — auto-opening the browser on poll was never going to work reliably.
  - **Offline** → **▶ Start** (starts server fire-and-forget) + **Apri →** (`<a href>`, always works)
  - **Online** → **Apri →** (colored, opens chat) + **■** stop button
  - Header **▶ Avvia tutto** starts all three servers in background

---

## [0.2.14] — 2026-05-26

### Fixed
- Launcher **▶ Avvia** now works correctly end-to-end:
  - Click → server starts in background, card shows **⏳ Avvio in corso…** spinner
  - The status poll (every 4 s) detects when the server is online
  - Browser opens automatically **only when the server is ready** — zero "connection refused"
  - Previously the browser opened immediately before the server was up, causing ERR_CONNECTION_REFUSED every time

---

## [0.2.13] — 2026-05-26

### Fixed
- Launcher **▶ Avvia** (offline state) now starts the server fire-and-forget via
  `POST /api/start/{key}` **and** immediately opens the browser in a new tab.
  No waiting, no spinner — browser opens instantly, page loads automatically
  once the server is ready (a few seconds). Previously the offline button was a
  plain `<a href>` that only opened the browser without starting the server,
  causing "connection refused" every time.

---

## [0.2.12] — 2026-05-26

### Fixed
- Launcher **▶ Avvia tutto** (header button) was calling the removed `launchModule()`
  function and throwing a `ReferenceError` in the browser console. Fixed to use
  `window.open()` directly — now opens all three module UIs in new tabs instantly,
  consistent with the per-card **▶ Avvia** buttons.

---

## [0.2.11] — 2026-05-26

### Fixed
- Launcher **▶ Avvia** button hung indefinitely waiting for the subprocess to
  come online. Simplified to: open the browser immediately (same as the old
  Open → button) and attempt server start fire-and-forget in background.
  No waiting, no blocking — click → browser opens instantly.

---

## [0.2.10] — 2026-05-26

### Changed
- Launcher UX redesign: removed the redundant Open/Start split.
  Each card now has **one button** that adapts to the server state:
  - Offline → **▶ Avvia** — starts the server AND opens the browser automatically
  - Online  → **Apri →** (navigate) + small **■** stop button
  - Mid-launch → spinner "Avvio in corso…"
  Header button renamed to **▶ Avvia tutto**.

---

## [0.2.9] — 2026-05-26

### Fixed
- Launcher **Start button** now works reliably on Windows/conda environments.
  `_resolve_cmd()` uses `shutil.which()` first, then searches the `Scripts/`
  directory next to `sys.executable` — covers conda, venv and global installs.
  Previously the subprocess couldn't find `ci-serve` when PATH wasn't inherited.
- Launcher JS: API error responses are now shown in the footer bar instead of
  silently failing. Button polling extended to 12 s (was 4.8 s). Stop button
  turns red on hover. `className` management replaced fragile regex with constants.

---

## [0.2.8] — 2026-05-26

### Added
- **`is-launch`** — new Launcher dashboard on port 8079 (`intelligence_ui/launcher.py`)
  - Single-page dashboard showing live status of all three modules (green/red dot, chunks count)
  - **Start / Stop** buttons per module — spawns `ci-serve`/`di-serve`/`mi-serve` as
    background subprocesses so you never need to open three separate terminals
  - **Start All** button in the header starts all three at once
  - Auto-polls `/health` every 4 seconds for live status
  - Direct **Open →** links to each module's chat UI
- **Multi-conversation sidebar** in the chat UI (`intelligence_ui/templates.py`)
  - **New Chat** button creates a fresh conversation (previous ones stay in the list)
  - Conversation history persisted to `localStorage` per module — survives page refreshes
  - Conversations grouped by date: Today / Yesterday / This week / Older
  - Click any conversation to restore full Q&A history
  - Hover ✕ button to delete individual conversations
  - Active conversation highlighted with left border accent
- `launcher_port: int = 8079` added to `intelligence_core/config.py`
- `LAUNCHER_PORT` documented in `.env.example`

---

## [0.2.7] — 2026-05-26

### Fixed
- Ollama LLM timeout was hardcoded to 120 s — complex questions on slow CPUs
  would return `[LLM error: timed out]` even though retrieval succeeded.
  Default raised to **300 s** and made configurable via `OLLAMA_TIMEOUT` in `.env`.

### Added
- `ollama_timeout: float = 300.0` in `intelligence_core/config.py`
- `OLLAMA_TIMEOUT=300` documented in `.env.example`

---

## [0.2.6] — 2026-05-26

### Changed
- Version bump only — identical to 0.2.5 content. Required because PyPI
  does not allow re-uploading a filename once it has been published.

---

## [0.2.5] — 2026-05-26

### Fixed
- `mi-serve` crash at startup: `path_templates.json` was missing from the
  installed wheel because setuptools does not include non-Python files by
  default. Added `[tool.setuptools.package-data]` to `pyproject.toml` so
  `MentorIntelligence/content/*.json` is now bundled in the wheel.
- `mi-ingest` was producing **1 chunk per file** (whole file truncated at
  3000 chars). `_parse_text_practice` now splits each Markdown file by `##`
  headings — **one chunk per section** — producing ~30 chunks from the four
  bundled guides instead of 4. Better granularity → better retrieval.

### Changed
- `README.md` — MentorIntelligence section updated with bundled `practices/`
  table and explanation of per-section chunking.

---

## [0.2.4] — 2026-05-26

### Added
- **`practices/` folder** — four Markdown guides specific to IntelligenceSuite
  onboarding and usage, ready to be ingested by MentorIntelligence:
  - `01_onboarding_nuovo_developer.md` — day-by-day setup, first indexing,
    architecture overview, team conventions, test suite
  - `02_come_usare_code_intelligence.md` — full CI pipeline, CLI commands,
    Python API, LLM config, troubleshooting
  - `03_come_usare_doc_intelligence.md` — DI supported formats, pipeline,
    example questions, Python API, confidence/escalation notes
  - `04_come_usare_mentor_intelligence.md` — MI onboarding flow, profile
    detection table, REST + Python API examples, recommended LLM config
- MentorIntelligence can now be bootstrapped with `mi-ingest ./practices`
  to answer onboarding questions about IntelligenceSuite itself

---

## [0.2.3] — 2026-05-26

### Added
- **Per-module LLM routing** — each module (CodeIntelligence, DocIntelligence,
  MentorIntelligence) can now use a different LLM backend, model, and endpoint
  independently via env vars:
  - `CI_LLM_BACKEND`, `CI_LLM_MODEL`, `CI_LLM_BASE_URL`, `CI_LLM_API_KEY`
  - `DI_LLM_BACKEND`, `DI_LLM_MODEL`, `DI_LLM_BASE_URL`, `DI_LLM_API_KEY`
  - `MI_LLM_BACKEND`, `MI_LLM_MODEL`, `MI_LLM_BASE_URL`, `MI_LLM_API_KEY`
  All variables are optional and fall back to the global `LLM_BACKEND` settings.
  Any OpenAI-compatible endpoint (vLLM, Groq, LM Studio, Azure…) works via
  `*_LLM_BACKEND=openai` + `*_LLM_BASE_URL`.
- `get_module_llm_provider(module)` factory in `intelligence_core/llm/__init__.py`
- `get_llm_provider()` now accepts `model`, `base_url`, `api_key` keyword overrides
- `.env.example` updated with documented per-module routing examples
- `docs/INTELLIGENCESUITE_GUIDE.md` — new comprehensive project guide added to `docs/`

### Docs
- README: new "Per-module LLM routing" section with full configuration example

---

## [0.2.2] — 2026-05-26

### Docs
- README fully updated for v0.2.x: all `.chroma/` references replaced with
  `~/.intelligence_suite/chroma`, "run from same directory" warnings removed,
  Ollama troubleshooting updated to reflect RuntimeError (no longer zero-vector),
  roadmap version table corrected, design principles table extended.

---

## [0.2.1] — 2026-05-26

### Fixed
- **Chat UI send button non-functional** — `onsubmit="submit(event)"` in the inline
  HTML attribute resolved to `HTMLFormElement.prototype.submit` (the native page-reload
  method) rather than our JavaScript function, because the form element's own `submit`
  property shadows `window.submit` in the inline handler scope chain.
  Fixed by removing the `onsubmit` attribute and wiring up the handler via
  `addEventListener('submit', ...)` on `DOMContentLoaded`.
- `useSuggestion()` now calls `sendMessage()` directly instead of dispatching a
  `submit` event (which had the same conflict).
- Chat suggestion pills now render on first health-check even when `/health` does not
  include a `module` field (backward compat with servers older than 0.2.0).
- `clearAll()` now recreates the `#suggestions` div and re-renders the pills after
  clearing the conversation.

---

## [0.2.0] — 2026-05-26

### Fixed
- **Zero vector silent storage** — `OllamaEmbedder._embed_single()` now raises
  `RuntimeError` with actionable instructions when Ollama is unreachable, instead of
  silently storing `[0.0] * 384` zero vectors in ChromaDB (which produced nonsense
  retrieval results). Users get a clear error pointing to `ollama serve` or
  `EMBED_BACKEND=st` as the fix.

### Changed
- **Absolute `CHROMA_PERSIST_DIR` default** — changed from `./.chroma` (relative,
  CWD-dependent) to `~/.intelligence_suite/chroma` (absolute, resolved at startup
  via `Path.expanduser().resolve()`). Data is now found regardless of which directory
  the server or CLI command is launched from. Override with `CHROMA_PERSIST_DIR=...`
  in `.env` if a custom location is needed.
- **Dynamic chat UI suggestion pills** — each server now reports its `module` field
  in `GET /health`; the chat UI reads this at boot and renders context-appropriate
  suggestion pills (code / doc / mentor questions) instead of hardcoded code examples.
- **CORS headers** — `CORSMiddleware` added to all three FastAPI apps; enables
  embedding the API in external dashboards or calling it from other origins.
- **`module` field in `/health`** — response now includes `"module": "code|doc|mentor"`
  so clients can identify which server they're talking to.

### Deprecated
- `intelligence_ui/chat_app.py` (Streamlit interface) — superseded by the built-in
  streaming chat UI at `http://localhost:808x/`. Will be removed in a future release.

---

## [0.1.9] — 2026-05-26

### Added
- `ST_MODEL` config setting — selects the SentenceTransformer model via `.env`
  Default: `all-MiniLM-L6-v2` (English). Set to `paraphrase-multilingual-MiniLM-L12-v2`
  for Italian / French / Spanish / German and 50+ other languages.
- `SentenceTransformerEmbedder` now reads `ST_MODEL` from settings automatically
- `.env.example`: multilingual model options documented with comments
- README: new Multilingual support section with model comparison table
- `get_embedder()` factory now accepts both `"st"` and `"sentence_transformer"` as backend name

---

## [0.1.8] — 2026-05-26

### Fixed
- `intelligence_ui` package was missing from `[tool.setuptools.packages.find]` include list —
  caused `ModuleNotFoundError: No module named 'intelligence_ui'` when opening the chat UI.

---

## [0.1.7] — 2026-05-26

### Fixed
- `asyncio.get_event_loop()` → `asyncio.get_running_loop()` in `_async_stream()`
  (deprecation warning in Python 3.10+)

### Docs
- README Quick Start updated: chat UI accessible at http://localhost:808x immediately
  after `ci-serve` / `di-serve` / `mi-serve` — no extra command needed

---

## [0.1.6] — 2026-05-26

### Added
- **Streaming chat UI** — open `http://localhost:808x` in any browser after starting a serve command
  - Real-time token streaming (SSE) — responses appear word by word
  - Left sidebar with numbered, clickable conversation history
  - Source citations as chips below each answer
  - Server health / chunk count / LLM backend status
  - Suggestion pills on welcome screen
  - Zero extra dependencies — served directly from the FastAPI server
- `POST /api/v1/stream` — new SSE endpoint on all three servers
- `GET /` — serves the chat HTML page from the RAG server
- `OllamaProvider.stream()` — sync token generator via httpx streaming
- `OpenAICompatProvider.stream()` — sync token generator via openai SDK streaming
- `intelligence_ui/templates.py` — self-contained HTML template (Tailwind CDN)

---

## [0.1.5] — 2026-05-26

### Added
- `intelligence_ui/chat_app.py` — Streamlit chat interface for all three modules
  - Left sidebar with clickable conversation history (numbered turns)
  - Module selector: Code / Doc / Mentor Intelligence
  - Live server health check with chunk count and LLM status
  - Source citations expandable below each answer
  - Latency / confidence / backend / escalation metadata per turn
  - Clear conversation button
- README: DocIntelligence and MentorIntelligence notebook examples
- `[ui]` extra: `pip install "intelligence-suite[ui]"`

---

## [0.1.4] — 2026-05-26

### Docs
- README: added Jupyter Notebook example section with real output from a test run

---

## [0.1.3] — 2026-05-26

### Fixed
- `ChromaStore.add()` now deduplicates chunk IDs before calling ChromaDB `upsert`.
  Prevents `DuplicateIDError` even if upstream parsers produce duplicate IDs.

---

## [0.1.2] — 2026-05-26

### Fixed
- `parse_repo` now excludes `build/`, `dist/`, `venv/`, `.venv/`, `node_modules/`,
  `.tox/`, `site-packages/`, `.eggs/`, `*.egg-info/` from indexing.
  Previously, running `python -m build` in the repo root caused `build/lib/` to be
  indexed alongside the real sources, producing duplicate chunk IDs and a
  `DuplicateIDError` in ChromaDB on `upsert`.

---

## [0.1.1] — 2026-05-26

### Fixed
- `Retriever.load_default()` now accepts `collection_name` parameter and connects to the
  correct ChromaDB collection (was defaulting to `"intelligence_suite"` — an empty collection —
  instead of `"code_intelligence"` / `"doc_intelligence"` / `"mentor_intelligence"`)

### Docs
- README: added ⚡ Quick Start section with Prerequisites, 3-command setup, and sample response
- README: fixed all Python API examples to pass `collection_name` explicitly
- README: clarified ChromaDB embedded mode (no separate server needed)
- README: added port numbers to CLI reference table

---

## [0.1.0] — 2026-05-26

### Added

**LLM provider layer** (`intelligence_core/llm/`)
- `LLMProvider` Protocol — unified interface for all generation backends
- `OllamaProvider` — local Ollama via `/api/chat`, no API key required
- `OpenAICompatProvider` — covers OpenAI, vLLM, Groq, Mistral AI, LM Studio, Azure, Together AI
- `ClaudeProvider` — Anthropic Messages API
- `get_llm_provider()` factory — reads `LLM_BACKEND` from `.env`; switch backend with zero code changes

**Configuration**
- `llm_backend`, `openai_*`, `claude_model` fields in `Settings`
- Separate default ports per module: `CI_PORT=8080`, `DI_PORT=8081`, `MI_PORT=8082` — run all three simultaneously
- `/health` endpoint reports `llm_backend` and `llm_available`
- `QueryResponse` gains `backend` field — callers know which LLM answered

**Modules**
- `CodeIntelligence` — Python AST parser + TypeScript/Go/SQL/YAML/Markdown regex parsers
- `DocIntelligence` — 3-level PDF parsing (pdfplumber → OCR → raw binary), DOCX, XLSX, TXT
- `MentorIntelligence` — adaptive onboarding: profile detection, session management, cross-domain orchestrator
- `intelligence_core` — unified chunk schema (`domain::type::locator`), ChromaDB store, embedder (Ollama / SentenceTransformer / Voyage), escalation policy, FastAPI base

**Examples** (`examples/`)
- `01_code_intelligence.py` — parse → embed → query a repository end-to-end
- `02_doc_intelligence.py` — ingest → embed → query documents end-to-end
- `03_switch_llm_backend.py` — demonstrate and compare all LLM backends at runtime

### Fixed
- `MentorIntelligence/orchestrator.py` — hardcoded Ollama httpx call replaced with `get_llm_provider()`
- `server_base.py` — replaced hardcoded `_call_local_llm` / `_call_claude` with `get_llm_provider()`
- `embed_chunks.py` / `embed_docs.py` — `input` argument now optional (defaults: `chunks.jsonl` / `doc_chunks.jsonl`)
- `pyproject.toml` — `sentence-transformers` moved from core `dependencies` to `[st]` extra; minimal install no longer pulls PyTorch
- `pyproject.toml` — missing `di-embed` CLI entry point added
- `pyproject.toml` — `license` updated to SPDX string format (setuptools ≥ 77 compatibility)
- README — configuration section now matches `.env.example` exactly
- README — Python API examples corrected (`retriever.search()`, `hit.chunk["key"]`)

### Package
- PyPI extras: `[st]`, `[openai]`, `[claude]`, `[pdf]`, `[ocr]`, `[docx]`, `[xlsx]`, `[all]`
- CLI entry points: `ci-parse`, `ci-embed`, `ci-serve`, `di-ingest`, `di-embed`, `di-serve`, `mi-ingest`, `mi-serve`
- Test suite: 54 passed, 5 skipped (KPI — require live indexed store), 0 failed
- Wheel: `intelligence_suite-0.1.0-py3-none-any.whl` — 54 KB, zero build warnings

---

## Roadmap

| Version | Planned |
|---|---|
| `0.2.0` | pgvector support · multi-tenant namespacing · streaming responses |
| `0.3.0` | ✅ **SkillIntelligence** — step-by-step procedural guidance with cross-domain RAG |
| `0.4.0` | pgvector · multi-tenant namespacing · JWT auth · Docker Compose |
| `0.5.0` | Graph layer (Neo4j) · hybrid vector+graph retrieval · async embedding queue |
| `1.0.0` | Production-grade · SLA-tested · full observability |
