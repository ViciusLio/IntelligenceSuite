# Changelog

All notable changes to IntelligenceSuite are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
