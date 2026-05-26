# Changelog

All notable changes to IntelligenceSuite are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
| `0.3.0` | GitHub Actions indexing webhook · incremental re-index |
| `1.0.0` | Production-grade · SLA-tested · full observability |
