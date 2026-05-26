# Changelog

All notable changes to IntelligenceSuite are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
