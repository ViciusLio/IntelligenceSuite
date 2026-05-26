# IntelligenceSuite — Complete Project Guide

## What is IntelligenceSuite?

IntelligenceSuite is a modular RAG (Retrieval-Augmented Generation) suite designed for
enterprise on-premise environments. It indexes source code and company documents, then
answers natural-language questions with precise source citations — fully local, zero cloud
required by default.

The core idea: instead of sending your entire codebase or documents to a cloud AI, you
index them locally into ChromaDB, embed them with a local model, and query them through
a local LLM (Ollama). The result is an on-premise knowledge retrieval system with
sub-second search and source-cited answers.

---

## The Three Modules

### CodeIntelligence

CodeIntelligence parses source code repositories into semantic chunks and exposes them
through a REST API and streaming chat UI. It supports Python (AST-based, precise),
TypeScript/JavaScript (regex), Go (regex), SQL, YAML, and Markdown.

The Python parser uses the `ast` module to extract exact function signatures, docstrings,
decorators, and call graphs. Each function, class, and module becomes an independent chunk
with a deterministic ID in the format `code::function::path/to/file.py::function_name`.

The CLI pipeline for CodeIntelligence:
- `ci-parse /path/to/repo` — walks the repo, runs language parsers, writes `chunks.jsonl`
- `ci-embed` — reads `chunks.jsonl`, sends each chunk to the embedding model, stores in ChromaDB
- `ci-serve` — starts the FastAPI server on port 8080

### DocIntelligence

DocIntelligence ingests company documents in multiple formats: PDF (3-level parsing
strategy), DOCX, XLSX, TXT, and Markdown. The 3-level PDF strategy tries pdfplumber
first (structured extraction), falls back to pytesseract OCR (for scanned documents),
and finally falls back to raw binary extraction — ensuring no page is ever silently lost.

The CLI pipeline for DocIntelligence:
- `di-ingest /path/to/docs` — ingests all documents, writes `doc_chunks.jsonl`
- `di-embed` — embeds chunks into ChromaDB collection `doc_intelligence`
- `di-serve` — starts the FastAPI server on port 8081

### MentorIntelligence

MentorIntelligence is the most complex module. It builds a personalised onboarding path
for each new team member based on their role and seniority. It uses cross-domain retrieval:
a single question is searched across the code, document, and mentor knowledge bases
simultaneously, and the results are fused into a coherent answer.

Key components:
- `profile_detector.py` — infers user profile (junior/senior developer, devops, analyst)
  from a free-text introduction
- `path_builder.py` — generates a structured learning path from the profile
- `session_manager.py` — persists session state as JSON on disk, survives restarts
- `orchestrator.py` — queries all three ChromaDB collections in parallel and fuses results

The CLI pipeline for MentorIntelligence:
- `mi-ingest ./practices` — ingests Markdown/TXT best practice documents
- `mi-serve` — starts the FastAPI server on port 8082

---

## The RAG Pipeline

Every module follows the same pipeline:

```
Source files
    ↓
Parser (domain-specific: Python AST, PDF pdfplumber, DOCX python-docx...)
    ↓
Chunks (JSONL — each chunk is self-contained, human-readable text)
    ↓
Embedder (Ollama nomic-embed-text, or SentenceTransformer, or Voyage AI)
    ↓
ChromaDB (persistent vector store, embedded in process)
    ↓
REST API / Chat UI (FastAPI + SSE streaming)
    ↓
User query → embed query → cosine similarity search → top-k results
    ↓
LLM (Ollama, OpenAI, Claude) → answer with source citations
```

---

## Chunk Schema

Every source file and document is converted into self-contained semantic chunks using
a universal schema:

```json
{
  "id":         "code::function::auth/jwt.py::verify_token",
  "domain":     "code",
  "type":       "function",
  "text":       "### verify_token\n\nValidates a JWT token...",
  "source":     "auth/jwt.py",
  "language":   "python",
  "metadata":   {"symbol": "verify_token", "start_line": 42, "end_line": 67},
  "embedding":  [0.012, -0.034, "..."],
  "indexed_at": "2026-05-26T10:22:00Z",
  "checksum":   "9ff7ac4fe71b"
}
```

The `id` field uses the pattern `domain::type::locator` which makes IDs deterministic
and safe to re-index — re-running the embedding pipeline on the same source produces
the same IDs, enabling incremental updates without duplicates.

---

## LLM Provider Architecture

IntelligenceSuite uses a `LLMProvider` Protocol to decouple answer generation from
any specific backend. All providers implement the same interface:
- `generate(question, context)` → str
- `stream(question, context)` → Iterator[str]
- `backend_name` → str
- `is_available()` → bool

Available providers:
- `OllamaProvider` — local Ollama via `/api/chat`, no API key, no GPU required
- `OpenAICompatProvider` — covers OpenAI, vLLM, Groq, Mistral AI, LM Studio, Azure
- `ClaudeProvider` — Anthropic Messages API

Switch backend with a single env var `LLM_BACKEND=ollama|openai|vllm|claude`.
No code changes required.

## Per-module LLM Routing

Each module can use a completely different LLM backend, model, and endpoint.
This allows optimal routing: a GPU-hosted code model for CodeIntelligence,
a multilingual model for DocIntelligence, and a high-quality cloud model for
MentorIntelligence — all running simultaneously on their respective ports.

Configure via per-module env vars (all optional, fall back to global settings):

```env
# CI_LLM_* — CodeIntelligence
CI_LLM_BACKEND=openai
CI_LLM_MODEL=codellama:34b
CI_LLM_BASE_URL=http://gpu-server:8000/v1
CI_LLM_API_KEY=

# DI_LLM_* — DocIntelligence
DI_LLM_BACKEND=ollama
DI_LLM_MODEL=mistral:7b

# MI_LLM_* — MentorIntelligence
MI_LLM_BACKEND=claude
MI_LLM_MODEL=claude-sonnet-4-5
```

The factory function `get_module_llm_provider(module)` reads these settings at
server startup and logs which backend is active for each module:

```
Module [CI] LLM override → backend=openai  model=codellama:34b  base_url=http://gpu-server:8000/v1
Module [DI] LLM override → backend=ollama  model=mistral:7b  base_url=(global)
Module [MI] LLM override → backend=claude  model=claude-sonnet-4-5  base_url=(global)
```

If no per-module override is set, the module uses the global `LLM_BACKEND` settings transparently.

---

## Embedding Backends

Three embedding backends are supported:
- `OllamaEmbedder` — default, uses `nomic-embed-text` via Ollama local server
- `SentenceTransformerEmbedder` — CPU-only, fully offline, no server needed.
  Model is controlled by `ST_MODEL` env var. Supports 50+ languages with
  `paraphrase-multilingual-MiniLM-L12-v2`.
- `ClaudeEmbedder` — Voyage AI embeddings (voyage-code-2 for code, voyage-3 for docs)

If the Ollama embedder cannot reach the server, it raises a `RuntimeError` immediately
with actionable fix instructions — it never silently stores zero vectors.

---

## Escalation Policy

When retrieval confidence (cosine similarity of the top result) falls below
`ESCALATION_THRESHOLD` (default 0.70), the system can automatically escalate the
question to Claude API for a higher-quality answer, regardless of the primary
`LLM_BACKEND` setting. This requires `ANTHROPIC_API_KEY` to be set.

The escalation decision is made in `intelligence_core/escalation.py` and the
`QueryResponse` includes an `escalated: bool` field so callers know which LLM answered.

---

## Streaming Chat UI

Each server (ci-serve, di-serve, mi-serve) serves a built-in streaming chat interface
at its root URL (`http://localhost:808x/`). No extra dependencies are required — it is
a self-contained HTML page with Tailwind CSS (CDN) served directly from the FastAPI server.

Features:
- Real-time token streaming via SSE (Server-Sent Events)
- Left sidebar with numbered, clickable conversation history
- Source citation chips below each answer (file · type · score)
- Server health, chunk count, and LLM backend displayed live
- Suggestion pills that adapt to the module (code/doc/mentor) by reading `/health`

The streaming is implemented via `POST /api/v1/stream` which returns an SSE stream.
The non-streaming endpoint `POST /api/v1/query` is also available for REST clients.

---

## Configuration

All settings are read from environment variables or a `.env` file:

```env
LLM_BACKEND=ollama              # ollama | openai | vllm | claude
OLLAMA_MODEL=qwen2.5-coder:7b
EMBED_BACKEND=ollama            # ollama | st | claude
OLLAMA_EMBED_MODEL=nomic-embed-text
CHROMA_PERSIST_DIR=~/.intelligence_suite/chroma   # absolute path (default)
ESCALATION_THRESHOLD=0.70
CI_PORT=8080
DI_PORT=8081
MI_PORT=8082
```

All three servers can run simultaneously on their respective ports.

---

## ChromaDB Storage

ChromaDB runs embedded inside the Python process — no separate server or Docker container
is needed. Data is persisted to `~/.intelligence_suite/chroma` by default (absolute path,
resolved at startup). This means all three modules share the same ChromaDB directory but
use separate named collections:
- `code_intelligence` — indexed by ci-embed
- `doc_intelligence` — indexed by di-embed
- `mentor_intelligence` — indexed by mi-embed

---

## API Endpoints

Every server exposes:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Streaming chat UI (HTML) |
| GET | `/health` | Server status, chunk count, LLM backend, module name |
| POST | `/api/v1/query` | Semantic search + LLM answer (non-streaming JSON) |
| POST | `/api/v1/stream` | Semantic search + LLM answer (SSE streaming) |
| GET | `/docs` | Interactive OpenAPI documentation |

MentorIntelligence adds:

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/mentor/onboard` | Start a new onboarding session |
| POST | `/api/v1/mentor/ask` | Ask within an existing session |
| GET | `/api/v1/mentor/progress/{session_id}` | Get onboarding progress |
| POST | `/api/v1/mentor/complete/{session_id}/{step_id}` | Mark a step complete |
| POST | `/api/v1/mentor/feedback` | Submit feedback on a step |
| POST | `/api/v1/mentor/reset/{session_id}` | Reset session to beginning |

---

## PyPI Package

IntelligenceSuite is published on PyPI as `intelligence-suite`. Install options:

```bash
pip install intelligence-suite                      # minimal (Ollama)
pip install "intelligence-suite[pdf,docx,xlsx]"    # document parsers
pip install "intelligence-suite[st]"               # offline embeddings
pip install "intelligence-suite[openai]"           # OpenAI / Groq / Mistral
pip install "intelligence-suite[claude]"           # Anthropic Claude
pip install "intelligence-suite[all]"              # everything
```

---

## Design Principles

- **On-premise first** — works 100% offline with Ollama + ChromaDB
- **Domain-aware chunking** — each chunk carries a `domain` field preventing cross-contamination
- **Deterministic IDs** — safe to re-index without creating duplicates
- **Fail-loud embedding** — raises immediately if embedding fails, never stores zero vectors
- **3-level PDF parsing** — never silently loses a page
- **Fail-safe ingestion** — one broken file never crashes the pipeline
- **Graceful escalation** — local LLM first, Claude API as optional fallback
- **CORS-enabled** — all servers include CORSMiddleware for cross-origin clients
- **Zero lock-in** — swap vector store, LLM, or embedder with a single env var change
