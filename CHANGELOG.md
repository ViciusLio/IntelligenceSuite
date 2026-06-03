# Changelog

All notable changes to IntelligenceSuite are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
