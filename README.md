# IntelligenceSuite

> **Retrieve enterprise knowledge in seconds, not hours.**

[![PyPI version](https://img.shields.io/pypi/v/intelligence-suite.svg)](https://pypi.org/project/intelligence-suite/)
[![Python 3.10+](https://img.shields.io/pypi/pyversions/intelligence-suite.svg)](https://pypi.org/project/intelligence-suite/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-54%20passed-brightgreen.svg)](tests/)

A modular RAG suite for enterprise on-premise environments.  
Index your codebase and company documents; query them in natural language with precise source citations.

**Zero mandatory cloud. Zero lock-in. Fully on-premise by default.**

```
code + docs  →  parse  →  chunks  →  embed  →  ChromaDB  →  REST API  →  natural-language answers
```

---

## ⚡ Quick Start

### Prerequisites

```bash
# 1. Ollama (local inference — no GPU required for embedding)
#    Download from https://ollama.com, then:
ollama serve
ollama pull nomic-embed-text      # embedding model
ollama pull qwen2.5-coder:7b      # generation model (or any other)
```

### Index your codebase in 3 commands

```bash
pip install intelligence-suite

ci-parse /path/to/your/repo       # parse → chunks.jsonl
ci-embed                           # embed → ChromaDB (local, no server needed)
ci-serve                           # REST API → http://localhost:8080
```

### Ask a question

```bash
curl -X POST http://localhost:8080/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Where is authentication handled?"}'
```

```json
{
  "answer": "Authentication is handled in auth/jwt.py — the verify_token function ...",
  "sources": [{"source": "auth/jwt.py", "type": "function", "score": 0.91}],
  "confidence": 0.91,
  "escalated": false,
  "backend": "ollama",
  "latency_ms": 312.4
}
```

> **No cloud, no API key, no GPU required** for the default setup.

---

## The problem it solves

How much time does your team lose every week hunting down where a function is implemented,
re-reading a 40-page procedure to recall one detail, or asking colleagues what an undocumented
service actually does?

Every AI assistant — local LLMs, Copilots, RAG agents — reasons on the context it receives.
Raw file dumps waste tokens on boilerplate and miss structure.

IntelligenceSuite turns your source code and company documents into **domain-aware semantic chunks** —
each self-contained, source-cited, and immediately embeddable — then serves them through a local
REST API you can query from any client.

---

## Modules

| Module | Domain | Status | Description |
|---|---|---|---|
| `intelligence_core` | Shared layer | ✅ Stable | Chunk schema, embedder, ChromaDB store, retriever, escalation policy |
| `CodeIntelligence` | Source code | ✅ Stable | Python AST + regex parsers for TS, Go, YAML, SQL, MD |
| `DocIntelligence` | Company docs | ✅ Stable | PDF (3-level), DOCX, XLSX, TXT ingest pipeline |
| `MentorIntelligence` | Onboarding | ✅ Stable | Adaptive onboarding — profile detection, sessions, cross-domain path |

---

## Installation

```bash
# Minimal — Ollama for both embeddings and generation (fully local)
pip install intelligence-suite

# With document parsers
pip install "intelligence-suite[pdf,docx,xlsx]"

# With OpenAI / vLLM / Groq / Mistral generation
pip install "intelligence-suite[openai]"

# With Claude generation + Voyage embeddings
pip install "intelligence-suite[claude]"

# With OCR support (requires tesseract on the system)
pip install "intelligence-suite[pdf,ocr]"

# Everything
pip install "intelligence-suite[all]"

# Development
pip install -e ".[dev]"
```

---

## CodeIntelligence — source code RAG

Parses your repository into semantic chunks, embeds them locally, and exposes a REST endpoint
to query your codebase in natural language.

### Supported languages

| Language | Parser | Extracts |
|---|---|---|
| **Python** | AST-based (precise) | modules, classes, methods, functions, decorators, async |
| **TypeScript / JS** | Regex | modules, classes, named + arrow functions |
| **Go** | Regex | packages, functions, method receivers, structs, interfaces |
| **SQL** | Regex | `CREATE TABLE / VIEW / FUNCTION / PROCEDURE / INDEX` |
| **YAML** | Heuristic | Docker Compose services, GitHub Actions jobs, K8s manifests |
| **Markdown** | Heading-based | H1 / H2 / H3 sections |

### CLI quickstart

```bash
# Index a repository
ci-parse /path/to/repo               # → chunks.jsonl
ci-embed                              # reads chunks.jsonl → ChromaDB

# Start the RAG server (default: http://localhost:8080)
ci-serve

# Query
curl -X POST http://localhost:8080/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Where is authentication handled?"}'
```

### Python API

```python
from pathlib import Path
from CodeIntelligence.parse_repo import parse_repo
from CodeIntelligence.embed_chunks import embed_chunks
from intelligence_core.retriever import Retriever

# 1. Parse and embed (one-time)
chunks = parse_repo(Path("/path/to/repo"), output=Path("chunks.jsonl"))
embed_chunks(Path("chunks.jsonl"))   # → ChromaDB "code_intelligence"

# 2. Query
retriever = Retriever.load_default(collection_name="code_intelligence")
results = retriever.search("Where is authentication handled?", domain="code", top_k=5)
for hit in results:
    print(f"[{hit.chunk['source']}] score={hit.score:.2f}  {hit.chunk['text'][:120]}")
```

---

## DocIntelligence — document RAG

Ingests company documents across multiple formats with a 3-level PDF parsing strategy
(structured → OCR → raw binary) and serves them through the same retrieval interface.

### Supported formats

| Format | Parser | Notes |
|---|---|---|
| **PDF** | pdfplumber → pytesseract → raw binary | 3-level fallback; heading detection via y-coordinates |
| **DOCX** | python-docx | Heading + body sections; empty sections preserved |
| **XLSX** | openpyxl | Sheet-by-sheet tabular chunks |
| **TXT / MD** | Built-in | Line-based or heading-based split |

### CLI quickstart

```bash
# Ingest documents (PDF, DOCX, XLSX, TXT, MD)
di-ingest /path/to/docs              # → doc_chunks.jsonl
di-embed                              # reads doc_chunks.jsonl → ChromaDB

# Start the doc server (default: http://localhost:8081)
di-serve

# Query
curl -X POST http://localhost:8081/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the production deploy prerequisites?"}'
```

### Python API

```python
from pathlib import Path
from DocIntelligence.ingest_docs import ingest_docs
from DocIntelligence.embed_docs import embed_docs
from intelligence_core.retriever import Retriever

# 1. Ingest and embed (one-time)
chunks = ingest_docs(Path("/path/to/docs"), output=Path("doc_chunks.jsonl"))
embed_docs(Path("doc_chunks.jsonl"))   # → ChromaDB "doc_intelligence"

# 2. Query
retriever = Retriever.load_default(collection_name="doc_intelligence")
results = retriever.search("Production deploy prerequisites", domain="doc", top_k=5)
for hit in results:
    print(f"[{hit.chunk['source']}] score={hit.score:.2f}  {hit.chunk['text'][:200]}")
```

---

## MentorIntelligence — adaptive onboarding

Builds a personalised onboarding path for each newcomer, combining knowledge from both the
codebase and company documents via cross-domain retrieval.

### Capabilities

| Feature | Description |
|---|---|
| **Profile detection** | Infers seniority and specialisation from the intro message |
| **Session management** | Persistent onboarding sessions with full question history |
| **Path builder** | Generates a structured learning path from profile + company practices |
| **Cross-domain orchestrator** | Retrieves from `code`, `doc`, and `mentor` domains in one query |
| **Practice ingestion** | Ingest team conventions, naming guides, and runbooks as mentor knowledge |

### CLI quickstart

```bash
# (Optional) ingest best practices
mkdir practices && echo "# Git conventions\n..." > practices/git.md
mi-ingest ./practices

# Start the mentor server (default: http://localhost:8082)
mi-serve

# Start an onboarding session
curl -X POST http://localhost:8082/api/v1/mentor/onboard \
  -H "Content-Type: application/json" \
  -d '{"user_name": "Alice", "intro": "I am a senior Python developer, first day here."}'

# Ask within your onboarding path
curl -X POST http://localhost:8082/api/v1/mentor/ask \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "question": "How does authentication work in this codebase?"}'
```

---

## What a chunk looks like

Every source file and every document is converted into self-contained **semantic chunks**
with a unified schema:

```json
{
  "id":         "code::function::myrepo/auth/jwt.py::verify_token",
  "domain":     "code",
  "type":       "function",
  "text":       "### verify_token\n\n**Description:** Validates a JWT and returns the decoded payload.\n```python\ndef verify_token(token: str) -> dict:\n    ...\n```",
  "source":     "auth/jwt.py",
  "language":   "python",
  "metadata": {
    "symbol":     "verify_token",
    "start_line": 42,
    "end_line":   67,
    "decorators": ["@router.get"],
    "calls":      ["jwt.decode", "raise_for_status"]
  },
  "embedding":  [0.012, -0.034, "..."],
  "indexed_at": "2025-05-01T10:22:00Z",
  "checksum":   "9ff7ac4fe71b"
}
```

### Valid domains and types

| Domain | Types |
|---|---|
| `code` | `module`, `class`, `function`, `method`, `config`, `schema` |
| `doc` | `section`, `table`, `paragraph` |
| `mentor` | `practice`, `path`, `session` |
| `api` | `endpoint`, `schema` |
| `data` | `table`, `view` |

---

## Integration examples

### Ollama — fully local, zero cost

```python
# .env: LLM_BACKEND=ollama  OLLAMA_MODEL=qwen2.5-coder:7b
from intelligence_core.retriever import Retriever
from intelligence_core.llm import get_llm_provider

retriever = Retriever.load_default(collection_name="code_intelligence")
llm       = get_llm_provider()          # reads LLM_BACKEND from .env

hits    = retriever.search("How is the database connection pooled?", domain="code", top_k=5)
context = "\n\n".join(h.chunk["text"] for h in hits)
answer  = llm.generate("How is the database connection pooled?", context)

print(answer)
for h in hits:
    print(f"  [{h.chunk['source']}] score={h.score:.2f}")
```

### OpenAI / Groq / Mistral / any OpenAI-compatible API

```python
# .env: LLM_BACKEND=openai  OPENAI_API_KEY=sk-...  OPENAI_MODEL=gpt-4o
from intelligence_core.llm import get_llm_provider
from intelligence_core.retriever import Retriever

retriever = Retriever.load_default(collection_name="doc_intelligence")
llm       = get_llm_provider()          # OpenAICompatProvider
# For Groq:      set OPENAI_BASE_URL=https://api.groq.com/openai/v1
# For Mistral:   set OPENAI_BASE_URL=https://api.mistral.ai/v1

hits   = retriever.search("Explain the payment flow", domain="doc", top_k=8)
answer = llm.generate("Explain the payment flow", "\n\n".join(h.chunk["text"] for h in hits))
```

### vLLM — local GPU server

```python
# .env: LLM_BACKEND=vllm
#        OPENAI_BASE_URL=http://localhost:8000/v1
#        OPENAI_MODEL=mistralai/Mistral-7B-Instruct-v0.2
from intelligence_core.llm import get_llm_provider

llm = get_llm_provider("vllm")   # OpenAI-compat client → your vLLM server
```

### Claude API

```python
# .env: LLM_BACKEND=claude  ANTHROPIC_API_KEY=sk-ant-...  CLAUDE_MODEL=claude-opus-4-5
from intelligence_core.llm import get_llm_provider
from intelligence_core.retriever import Retriever

retriever = Retriever.load_default(collection_name="code_intelligence")
llm       = get_llm_provider("claude")

hits   = retriever.search("Explain the entire auth flow", domain="code", top_k=8)
answer = llm.generate("Explain the entire auth flow", "\n\n".join(h.chunk["text"] for h in hits))
```

### LangChain / LlamaIndex

```python
from intelligence_core.retriever import Retriever
from langchain.schema import Document

retriever = Retriever.load_default(collection_name="doc_intelligence")
hits = retriever.search("Deploy prerequisites", domain="doc", top_k=10)

docs = [
    Document(
        page_content=h.chunk["text"],
        metadata={
            "source": h.chunk["source"],
            "domain": h.chunk["domain"],
            "type":   h.chunk["type"],
        },
    )
    for h in hits
]
# → pass docs to any LangChain chain or LlamaIndex index
```

---

## LLM backends (generation)

IntelligenceSuite uses a provider-agnostic `LLMProvider` protocol for answer generation.
Switch backend with a single env var — no code changes required.

| Backend | `LLM_BACKEND` | Extra | Notes |
|---|---|---|---|
| **Ollama** | `ollama` | *(none)* | Default — fully local, no API key, no GPU required |
| **OpenAI** | `openai` | `[openai]` | GPT-4o, GPT-4o-mini, o1, … |
| **vLLM** | `vllm` | `[openai]` | Local GPU server, OpenAI-compatible; set `OPENAI_BASE_URL` |
| **Claude** | `claude` | `[claude]` | Anthropic claude-opus-4-5, claude-sonnet-4-5, … |
| **Groq** | `openai` | `[openai]` | Fast inference; set `OPENAI_BASE_URL=https://api.groq.com/openai/v1` |
| **Mistral AI** | `openai` | `[openai]` | Set `OPENAI_BASE_URL=https://api.mistral.ai/v1` |
| **LM Studio** | `vllm` | `[openai]` | Local; set `OPENAI_BASE_URL=http://localhost:1234/v1` |

> Any OpenAI-compatible server works with `LLM_BACKEND=openai` or `vllm` by pointing
> `OPENAI_BASE_URL` at the correct endpoint.

### Escalation

When retrieval confidence < `ESCALATION_THRESHOLD` and `ANTHROPIC_API_KEY` is set,
the system automatically escalates to Claude — regardless of the primary `LLM_BACKEND`.

## Embedding backends

| Backend | `EMBED_BACKEND` | Extra | Notes |
|---|---|---|---|
| **Ollama** | `ollama` | *(none)* | Default — fully local |
| **SentenceTransformer** | `st` | `[st]` | CPU-only, fully offline, no Ollama needed |
| **Claude / Voyage** | `claude` | `[claude]` | Cloud embeddings via Voyage AI |

### Vector store

| Store | Status | Notes |
|---|---|---|
| **ChromaDB** | ✅ Default | Embedded — runs inside the Python process, persists to `.chroma/` |
| **pgvector** | 🔶 Roadmap | Enterprise, multi-tenant |

> ChromaDB runs **embedded** — no separate server or Docker container needed.  
> Data is persisted to `.chroma/` automatically and survives restarts.

---

## Design principles

| Principle | Implementation |
|---|---|
| **On-premise first** | Ollama + ChromaDB by default — no cloud required |
| **Domain-aware chunking** | Every chunk carries `domain` — prevents cross-contamination in retrieval |
| **Deterministic IDs** | `domain::type::locator` — safe to re-index, dedup-friendly |
| **3-level PDF parsing** | pdfplumber → OCR → raw binary — never silently drops a page |
| **Fail-safe ingestion** | One broken file never crashes the pipeline |
| **Graceful escalation** | Stays local until similarity drops below threshold, then escalates to Claude API |
| **Modular** | Each module is independently installable and deployable |

---

## Configuration

Copy `.env.example` to `.env` and edit:

```env
# LLM generation (ollama | openai | vllm | claude)
LLM_BACKEND=ollama
OLLAMA_MODEL=qwen2.5-coder:7b

# OpenAI-compatible (OpenAI, vLLM, Groq, Mistral, LM Studio…)
# OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4o
# OPENAI_BASE_URL=https://api.openai.com/v1   # vLLM: http://localhost:8000/v1

# Claude
# ANTHROPIC_API_KEY=sk-ant-...
# CLAUDE_MODEL=claude-opus-4-5

# Embeddings (ollama | st | claude)
EMBED_BACKEND=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=nomic-embed-text

# Vector store
VECTOR_STORE=chromadb
CHROMA_PERSIST_DIR=./.chroma

# Escalation: fallback to Claude when confidence < threshold
ESCALATION_THRESHOLD=0.70

# Server ports — all three can run simultaneously
CI_PORT=8080   # CodeIntelligence
DI_PORT=8081   # DocIntelligence
MI_PORT=8082   # MentorIntelligence
```

All variables are accepted as plain environment variables too — no `.env` file required in CI/CD.

### CLI reference

| Command | Module | Action |
|---|---|---|
| `ci-parse <repo>` | CodeIntelligence | Parse repository into chunks → `chunks.jsonl` |
| `ci-embed [file]` | CodeIntelligence | Embed chunks into ChromaDB (default: `chunks.jsonl`) |
| `ci-serve` | CodeIntelligence | Start the code RAG server on `CI_PORT` (default 8080) |
| `di-ingest <dir>` | DocIntelligence | Ingest documents into chunks → `doc_chunks.jsonl` |
| `di-embed [file]` | DocIntelligence | Embed doc chunks into ChromaDB (default: `doc_chunks.jsonl`) |
| `di-serve` | DocIntelligence | Start the doc RAG server on `DI_PORT` (default 8081) |
| `mi-ingest <dir>` | MentorIntelligence | Ingest best practice documents |
| `mi-serve` | MentorIntelligence | Start the mentor server on `MI_PORT` (default 8082) |

---

## KPI targets

| Metric | CodeIntelligence | DocIntelligence |
|---|---|---|
| Hit@1 | > 60% | > 55% |
| Hit@5 | > 85% | > 80% |
| MRR | > 0.70 | > 0.65 |
| Latency P50 | < 300 ms | < 400 ms |
| Latency P99 | < 2 000 ms | < 2 000 ms |

> KPI tests are included in the suite and skipped automatically until a live indexed store is present.

---

## Hardware requirements

| Scenario | Hardware |
|---|---|
| Dev / local testing | Mac or PC, 16 GB RAM |
| Team 1–10 | Linux server, 32 GB RAM |
| Team 10–50 (GPU) | RTX 3090/4090 + 64 GB RAM |
| Team 50+ | pgvector (roadmap) + dedicated GPU |

---

## Test suite

```bash
pip install -e ".[dev]"
pytest tests/ -v
# 54 passed, 5 skipped (KPI — require indexed store), 0 failed
```

---

## Architecture

```
IntelligenceSuite/
├── intelligence_core/       # Shared: chunk schema, embedder, ChromaDB, retriever, escalation
├── CodeIntelligence/        # Code RAG: Python AST, TS, Go, YAML, SQL, MD parsers
├── DocIntelligence/         # Doc RAG: PDF (3-level), DOCX, XLSX, TXT
└── MentorIntelligence/      # Adaptive onboarding: profile, session, path, orchestrator
```

---

## Roadmap

| Version | Milestone |
|---|---|
| `0.1.x` | CodeIntelligence · DocIntelligence · MentorIntelligence · ChromaDB — **current** |
| `0.2.0` | pgvector support · multi-tenant namespacing |
| `0.3.0` | Streaming responses · WebSocket push notifications |
| `0.4.0` | GitHub Actions indexing webhook · incremental re-index |
| `1.0.0` | Production-grade · SLA-tested · full observability |

---

## License

MIT — see [LICENSE](LICENSE)

---

> See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions and [docs/](docs/) for presentations.
