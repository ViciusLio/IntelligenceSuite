# IntelligenceSuite

> **Retrieve enterprise knowledge in seconds, not hours.**

[![PyPI version](https://img.shields.io/pypi/v/intelligence-suite.svg)](https://pypi.org/project/intelligence-suite/)
[![Python 3.10+](https://img.shields.io/pypi/pyversions/intelligence-suite.svg)](https://pypi.org/project/intelligence-suite/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-258%20passed-brightgreen.svg)](tests/)

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
# Ollama (local inference — no GPU required for embedding)
# Download from https://ollama.com, then:
ollama serve
ollama pull nomic-embed-text      # embedding model
ollama pull qwen2.5-coder:7b      # generation model (or any other)
```

### Option A — Launcher (recommended)

One command starts a dashboard that manages every module.

```bash
pip install intelligence-suite

is-launch          # opens http://localhost:8079 in your browser
```

Each card on the launcher page has two controls:
- **Offline** → **▶ Start** runs the server in the background, then **Apri →** opens the chat UI
  (start first, wait a few seconds for the dot to turn green, then open)
- **Online** → **Apri →** opens the chat UI directly + **■** stops the server

The header **▶ Avvia tutto** button starts all servers at once — no extra terminals needed.

> **First time?** Index your content before starting the servers:
> ```bash
> ci-parse /path/to/repo && ci-embed   # CodeIntelligence (one-time)
> di-ingest /path/to/docs && di-embed  # DocIntelligence  (one-time)
> mi-ingest ./practices                # MentorIntelligence (one-time)
> ```

### Option B — Individual servers

```bash
ci-parse /path/to/your/repo       # parse → chunks.jsonl        (seconds)
ci-embed                           # embed → ChromaDB            (one-time, ~20-40 min CPU)
ci-serve                           # REST API + Chat UI → http://localhost:8080
```

> **`ci-embed` is slow the first time** (every chunk is sent to the embedding model).
> ChromaDB persists the result to **`~/.intelligence_suite/chroma`** (absolute path — safe
> to run from any working directory). Subsequent server restarts are **instant**.

### Chat UI

Once any server is running, open its URL — the chat interface loads instantly.

- Responses **stream word by word** in real-time (SSE)
- **Multi-conversation sidebar** — New Chat button, full history per module
- Conversations **persist across page refreshes** (localStorage per module)
- **Source citations** as chips below each answer (file · type · score)
- Server status, chunk count, LLM backend displayed live
- Zero extra dependencies — served directly from the RAG server

### Or query via REST API

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

| Module | Domain | Description |
|---|---|---|
| `intelligence_core` | Shared layer | Chunk schema, embedder, ChromaDB store, retriever, escalation policy, RAGAS evaluation, dependency graph (GraphRAG) |
| `CodeIntelligence` | Source code | Python AST + Tree-sitter parsers for TS, Go, Java, Rust (regex fallback), YAML, SQL, MD |
| `DocIntelligence` | Company docs | PDF (3-level), DOCX, XLSX, TXT ingest pipeline |
| `MentorIntelligence` | Onboarding | Adaptive onboarding — profile detection, sessions, cross-domain path |
| `SkillIntelligence` | Procedures | Step-by-step procedural guidance with cross-domain RAG (code + doc + mentor) |
| `AgentIntelligence` | Multi-hop agent | ReAct agent with tool calling (search_code/docs/practices, analyze_impact) |

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

# Tree-sitter multilanguage parsers (TypeScript, Go, Java, Rust)
pip install "intelligence-suite[multilang]"

# Dependency graph + GraphRAG context expansion
pip install "intelligence-suite[graph]"

# RAGAS evaluation pipeline (ci-eval)
pip install "intelligence-suite[eval]"

# Everything (core extras — does not include eval/multilang, kept opt-in)
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
| **Python** | AST-based (precise) | modules, classes, methods, functions, decorators, async, call graph |
| **TypeScript / JS** | Tree-sitter¹ (regex fallback) | functions, methods, call sites |
| **Go** | Tree-sitter¹ (regex fallback) | functions, method receivers, call sites |
| **Java** | Tree-sitter¹ | methods, constructors, call sites |
| **Rust** | Tree-sitter¹ | functions (incl. `impl` methods), call sites |
| **SQL** | Regex | `CREATE TABLE / VIEW / FUNCTION / PROCEDURE / INDEX` |
| **YAML** | Heuristic | Docker Compose services, GitHub Actions jobs, K8s manifests |
| **Markdown** | Heading-based | H1 / H2 / H3 sections |

¹ Requires the `[multilang]` extra. When not installed, TypeScript/JS and Go fall back to the
regex parsers automatically — zero breaking changes. Tree-sitter parsers also extract `calls`
metadata, which powers the dependency graph (`[graph]`).

### CLI quickstart

```bash
ci-parse /path/to/repo               # → chunks.jsonl                  (seconds)
ci-embed                              # → ~/.intelligence_suite/chroma  (slow, one-time)
ci-embed --incremental                # re-embed only new chunks
ci-serve                              # http://localhost:8080

# Query via curl:
curl -X POST http://localhost:8080/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Where is authentication handled?"}'
```

> ChromaDB data is stored in **`~/.intelligence_suite/chroma`** (absolute path, resolved at
> startup). Run commands from any directory — the data is always found.
> Override with `CHROMA_PERSIST_DIR=/custom/path` in `.env` if needed.

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
di-ingest /path/to/docs              # → doc_chunks.jsonl              (seconds)
di-embed                              # → ~/.intelligence_suite/chroma  (slow, one-time)
di-embed --incremental                # re-index only new files
di-serve                              # http://localhost:8081

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

chunks = ingest_docs(Path("/path/to/docs"), output=Path("doc_chunks.jsonl"))
embed_docs(Path("doc_chunks.jsonl"))   # → ChromaDB "doc_intelligence"

retriever = Retriever.load_default(collection_name="doc_intelligence")
results = retriever.search("Production deploy prerequisites", domain="doc", top_k=5)
for hit in results:
    print(f"[{hit.chunk['source']}] score={hit.score:.2f}  {hit.chunk['text'][:200]}")
```

---

## MentorIntelligence — adaptive onboarding

Builds a personalised onboarding path for each newcomer, combining knowledge from both the
codebase and company documents via cross-domain retrieval.

| Feature | Description |
|---|---|
| **Profile detection** | Infers seniority and specialisation from the intro message |
| **Session management** | Persistent onboarding sessions with full question history |
| **Path builder** | Generates a structured learning path from profile + company practices |
| **Cross-domain orchestrator** | Retrieves from `code`, `doc`, and `mentor` domains in one query |
| **Practice ingestion** | Ingest team conventions, naming guides, and runbooks as mentor knowledge |

### CLI quickstart

```bash
mi-ingest ./practices                 # ingest best practices (Markdown / TXT / YAML)
mi-serve                              # http://localhost:8082

# Start an onboarding session
curl -X POST http://localhost:8082/api/v1/mentor/onboard \
  -H "Content-Type: application/json" \
  -d '{"user_name": "Alice", "intro": "I am a senior Python developer, first day here."}'

# Ask within your onboarding path
curl -X POST http://localhost:8082/api/v1/mentor/ask \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "question": "How does authentication work in this codebase?"}'
```

The repository ships a ready-to-use `practices/` folder documenting IntelligenceSuite itself —
each file is split by `##` headings at ingest time (one chunk per section) for precise retrieval.

---

## SkillIntelligence — procedural guidance with RAG

Transforms company procedures into interactive step-by-step guidance sessions.
Each step retrieves context from the code, doc, and mentor knowledge bases before
generating LLM guidance — grounded in your actual company knowledge.

```
Markdown / Python skill definition
        ↓
SkillRegistry  (auto-discovers skills)
        ↓
SkillExecutor.start_session(skill, params)
        ↓  cross-domain retrieval (code + doc + mentor)
        ↓  LLM guidance generation (RAG-grounded)
        ↓
SkillResult  {step_id, title, guidance, sources, is_last_step, session_id}
        ↓
... executor.next_step(session_id) ...
```

### CLI quickstart

```bash
si-serve                              # http://localhost:8083
si-ingest ./skill_docs                # load / list Markdown skills

curl -X POST http://localhost:8083/api/v1/skill/start \
  -H "Content-Type: application/json" \
  -d '{"skill_name": "deploy_checklist",
       "parameters": {"service_name": "api", "environment": "staging"}}'

curl -X POST http://localhost:8083/api/v1/skill/next \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "user_input": "done"}'
```

### Define a skill in Markdown

```markdown
# Skill: My Deploy Checklist
> description: Guide the team through a production deploy.
> parameters: service_name (str, required), environment (str, required, enum: staging|production)

## Step 1: Pre-flight checks
**Domini:** doc, code
**Query:** pre-deploy checklist {service_name} {environment}
Verify all CI checks pass and the changelog is updated.

## Step 2: Deploy
**Domini:** doc
**Query:** deploy procedure {service_name}
Run the deployment script and confirm the health check turns green.
```

Save the file anywhere (e.g. `skill_docs/my_deploy.md`) — it is picked up automatically at server start.

### Define a skill in Python

```python
from SkillIntelligence.base import BaseSkill, SkillStep

class DeployChecklist(BaseSkill):
    name = "deploy_checklist"
    description = "Step-by-step production deploy guidance"
    parameters = {
        "service_name": {"type": "str", "required": True},
        "environment":  {"type": "str", "required": True, "enum": ["staging", "production"]},
    }
    steps = [
        SkillStep(id="step_1", title="Pre-flight checks",
                  description="Verify CI, changelog, feature flags",
                  knowledge_query="pre-deploy checklist {service_name} {environment}",
                  domains=["code", "doc"]),
        SkillStep(id="step_2", title="Deploy",
                  description="Execute the deployment",
                  knowledge_query="deploy procedure {service_name}",
                  domains=["doc"]),
    ]
```

Place the file in `SkillIntelligence/skills/` — it is imported and registered automatically.

### REST API reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Module status + skills count + LLM availability |
| `/api/v1/skill/list` | GET | List all registered skills with metadata |
| `/api/v1/skill/start` | POST | Start a new session → first step guidance + sources |
| `/api/v1/skill/next` | POST | Advance to next step (`completed: true` when done) |
| `/api/v1/skill/session/{id}` | GET | Current session metadata (step index, total steps) |

Sessions are stored as JSON files in `~/.intelligence_suite/skill_sessions/`, survive server
restarts, and are deleted automatically when all steps are completed.

---

## AgentIntelligence — multi-hop ReAct agent

For questions a single retrieval can't answer ("what breaks if I change function X?",
"compare how auth works in the code vs the docs"), AgentIntelligence runs a real **ReAct loop**:
it reasons, calls tools, observes results, and iterates until it can answer.

| Tool | Purpose |
|---|---|
| `search_code` | Semantic search over the code domain |
| `search_docs` | Semantic search over the doc domain |
| `search_practices` | Semantic search over the mentor domain |
| `analyze_impact` | Walks the reverse call graph — "what depends on this?" (requires `[graph]`) |

```bash
ai-serve                              # http://localhost:8084

curl -X POST http://localhost:8084/api/v1/agent/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What breaks if I change the verify_token function?"}'
```

The agent is also reachable transparently through Intent Routing (see below) when a query is
classified as a complex multi-domain analysis.

---

## Intent Routing

Every `/api/v1/query` request is transparently classified before being answered. The user writes
in the chat as always; the routing is invisible.

| Level | When | Result |
|---|---|---|
| **RAG** | Simple factual question | Standard retrieval + LLM answer |
| **SKILL** | Procedural request ("guide me", "step by step", "how do I…") | SkillSession started, first step returned as text |
| **AGENT** | Complex multi-domain analysis | ReAct agent — multi-hop tool calling; enable with `INTENT_AGENT_ENABLED=true` |

**Two-stage classification:**
1. **Heuristic (0 ms, no LLM call)** — keyword triggers and structural rules. If confidence ≥ 0.85 the result is used directly.
2. **LLM call (~300 ms)** — minimal prompt, called only for ambiguous cases (confidence < 0.85).

Any failure (LLM timeout, bad JSON, network error) silently falls back to RAG — the request
always gets an answer. Disable entirely with `INTENT_ROUTING=false` in `.env`.

When routing detects a SKILL intent but cannot extract all required parameters, it asks the user
in natural language instead of starting the session.

---

## Dependency graph & GraphRAG (`[graph]`)

CodeIntelligence chunks carry `calls` / `imports` / `bases` metadata. The `[graph]` extra builds a
directed dependency graph from them with NetworkX, persisted to `~/.intelligence_suite/graph/`.

```bash
pip install "intelligence-suite[graph]"

ci-graph --stats                 # build the graph and print node/edge stats
ci-graph --top-critical 10       # show the 10 most-called functions (impact hotspots)
```

Once the graph exists, the retriever automatically performs **GraphRAG**: after the semantic search
it expands the context with structurally-related nodes (callers + callees) of the top hits. Fully
optional and non-breaking — if the graph is missing or fails, retrieval proceeds unchanged. The
agent's `analyze_impact` tool answers "what breaks if I change function X?" by walking the reverse
call graph.

---

## RAG quality evaluation with RAGAS (`[eval]`)

Measure retrieval/answer quality objectively on four dimensions: faithfulness, answer relevancy,
context precision, context recall.

```bash
pip install "intelligence-suite[eval]"

ci-eval --domain code --samples 50          # generate testset, run, score
ci-eval --domain doc --regenerate           # force-regenerate the cached testset
```

KPI targets: faithfulness ≥ 0.75, answer_relevancy ≥ 0.75, context_precision ≥ 0.70,
context_recall ≥ 0.68. Reports are saved under `~/.intelligence_suite/eval/` with a delta vs the
previous run; the command exits non-zero if any target is missed (CI-friendly).

---

## What a chunk looks like

Every source file and document is converted into self-contained **semantic chunks** with a
unified schema:

```json
{
  "id":         "code::function::myrepo.auth.jwt.verify_token",
  "domain":     "code",
  "type":       "function",
  "text":       "### verify_token\n\n```python\ndef verify_token(token: str) -> dict:\n    ...\n```",
  "source":     "auth/jwt.py",
  "language":   "python",
  "metadata": {
    "name":       "verify_token",
    "line_start": 42,
    "line_end":   67,
    "calls":      ["jwt.decode", "raise_for_status"],
    "imports":    ["jwt"]
  }
}
```

### Valid domains and types

| Domain | Types |
|---|---|
| `code` | `function`, `class`, `interface`, `config_block`, `module`, `file` |
| `doc` | `section`, `table`, `paragraph` |
| `mentor` | `practice`, `onboarding_step`, `role_guide`, `faq`, `glossary` |

The chunk ID is deterministic — `domain::type::locator` — so re-indexing is idempotent and dedup-friendly.

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

### Per-module LLM routing

Each module can use a **different LLM backend and model** independently.
Set any combination of `CI_LLM_*`, `DI_LLM_*`, `MI_LLM_*` in `.env` — leave empty to fall back to the global `LLM_BACKEND`:

```env
# CodeIntelligence → vLLM GPU server with code-specialised model
CI_LLM_BACKEND=openai
CI_LLM_MODEL=codellama:34b
CI_LLM_BASE_URL=http://gpu-server:8000/v1

# DocIntelligence → local Mistral (better multilingual / Italian)
DI_LLM_BACKEND=ollama
DI_LLM_MODEL=mistral:7b

# MentorIntelligence → Claude API (best pedagogical quality)
MI_LLM_BACKEND=claude
MI_LLM_MODEL=claude-sonnet-4-5
```

### Escalation

When retrieval confidence < `ESCALATION_THRESHOLD` and `ANTHROPIC_API_KEY` is set, the system
automatically escalates to Claude — regardless of the primary `LLM_BACKEND`.

---

## Embedding backends

| Backend | `EMBED_BACKEND` | Extra | Notes |
|---|---|---|---|
| **Ollama** | `ollama` | *(none)* | Default — fully local |
| **SentenceTransformer** | `st` | `[st]` | CPU-only, fully offline, no Ollama needed |
| **Claude / Voyage** | `claude` | `[claude]` | Cloud embeddings via Voyage AI |

### Multilingual support

By default the embedding model is English-optimised. To query and answer in Italian (or any of
50+ languages), switch to a multilingual SentenceTransformer model:

```env
EMBED_BACKEND=st
ST_MODEL=paraphrase-multilingual-MiniLM-L12-v2   # 50+ languages, same speed as default
```

| Model | Languages | Dimensions | Speed |
|---|---|---|---|
| `all-MiniLM-L6-v2` | English only | 384 | ⚡ Fast (default) |
| `paraphrase-multilingual-MiniLM-L12-v2` | 50+ (IT, FR, ES, DE, …) | 384 | ⚡ Fast |
| `paraphrase-multilingual-mpnet-base-v2` | 50+ | 768 | 🐢 Slower, higher quality |

> **Note:** switching embedding model requires re-indexing from scratch — the vector dimensions
> may change (384 → 768) and ChromaDB will reject mixed-dimension collections. Delete the data
> directory before re-running `ci-embed`:
> ```bash
> rm -rf ~/.intelligence_suite/chroma                              # Linux / macOS
> Remove-Item -Recurse -Force "$HOME\.intelligence_suite\chroma"   # Windows PowerShell
> ```

### Vector store

ChromaDB runs **embedded** — no separate server or Docker container needed. Data persists to
`~/.intelligence_suite/chroma` automatically and survives restarts. Override the path with
`CHROMA_PERSIST_DIR=/your/path` in `.env`.

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

# Vector store — default path: ~/.intelligence_suite/chroma (absolute, CWD-independent)
VECTOR_STORE=chromadb
# CHROMA_PERSIST_DIR=/custom/path/chroma

# Escalation: fallback to Claude when confidence < threshold
ESCALATION_THRESHOLD=0.70

# Intent routing
INTENT_ROUTING=true
INTENT_AGENT_ENABLED=true

# Server ports — all five can run simultaneously
CI_PORT=8080      # CodeIntelligence
DI_PORT=8081      # DocIntelligence
MI_PORT=8082      # MentorIntelligence
SI_PORT=8083      # SkillIntelligence
AGENT_PORT=8084   # AgentIntelligence
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
| `si-ingest <dir>` | SkillIntelligence | Load / list Markdown skills from a directory |
| `si-serve` | SkillIntelligence | Start the skill guidance server on `SI_PORT` (default 8083) |
| `ai-serve` | AgentIntelligence | Start the ReAct agent server on `AGENT_PORT` (default 8084) |
| `ci-eval` | intelligence_core | Run the RAGAS evaluation pipeline (requires `[eval]`) |
| `ci-graph` | intelligence_core | Build the dependency graph + stats (requires `[graph]`) |
| `is-launch` | Launcher | Dashboard to start/stop/monitor all modules — port 8079 |

---

## Design principles

| Principle | Implementation |
|---|---|
| **On-premise first** | Ollama + ChromaDB by default — no cloud required |
| **Domain-aware chunking** | Every chunk carries `domain` — prevents cross-contamination in retrieval |
| **Deterministic IDs** | `domain::type::locator` — safe to re-index, dedup-friendly |
| **3-level PDF parsing** | pdfplumber → OCR → raw binary — never silently drops a page |
| **Fail-safe ingestion** | One broken file never crashes the pipeline |
| **Fail-loud embedding** | `OllamaEmbedder` raises immediately if unreachable — never stores zero vectors |
| **Graceful escalation** | Stays local until similarity drops below threshold, then escalates to Claude API |
| **Non-breaking extras** | Tree-sitter, graph, and eval are opt-in — absence degrades gracefully, never crashes |
| **CORS-enabled API** | All FastAPI servers include `CORSMiddleware` — embeddable in any dashboard |

---

## Troubleshooting

### CLI scripts not found after install (Windows)

pip installs CLI scripts in a user-level Scripts folder that may not be on `PATH`. Add it once:

```powershell
$scripts = "$env:APPDATA\Python\$(python -c 'import sys; print(f\"Python{sys.version_info.major}{sys.version_info.minor}\")')\Scripts"
$current = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($current -notlike "*$scripts*") {
    [Environment]::SetEnvironmentVariable("PATH", "$current;$scripts", "User")
    Write-Host "PATH updated — reopen your terminal."
}
```

Or run modules directly without touching PATH: `python -m CodeIntelligence.rag_server`, etc.

### Ollama not reachable during embedding

If `ci-embed` / `di-embed` raises a `RuntimeError`, Ollama is not running or the model is not
pulled. The embedder **fails loudly** (no silent zero-vector storage):

```bash
ollama serve && ollama pull nomic-embed-text   # Fix 1: start Ollama
# Fix 2: set EMBED_BACKEND=st in .env (offline, no server required)
```

### ChromaDB DuplicateIDError on embed

Your `chunks.jsonl` contains duplicate IDs — usually because `python -m build` was run inside the
repo before indexing, so `build/lib/` got indexed alongside the real sources.

```bash
rm -rf build/ dist/ ~/.intelligence_suite/chroma
ci-parse /path/to/repo && ci-embed
```

From `0.1.2` onwards, `parse_repo` automatically excludes `build/`, `dist/`, `venv/`, and other
non-source directories.

---

## Test suite

```bash
pip install -e ".[dev]"
pytest tests/ -v
# 258 passed, 5 skipped (KPI — require indexed store), 0 failed
```

---

## Architecture

```
IntelligenceSuite/
├── intelligence_core/       # Shared layer
│   ├── parsers/             #   class-based Tree-sitter parsers (TS, Go, Java, Rust)
│   ├── graph/               #   NetworkX dependency graph + GraphRAG + ci-graph CLI
│   └── evaluation/          #   RAGAS pipeline (ci-eval)
├── CodeIntelligence/        # Code RAG: Python AST + Tree-sitter/regex, YAML, SQL, MD parsers
├── DocIntelligence/         # Doc RAG: PDF (3-level), DOCX, XLSX, TXT
├── MentorIntelligence/      # Adaptive onboarding: profile, session, path, orchestrator
├── SkillIntelligence/       # Procedural guidance: skill registry, executor, cross-domain RAG
│   └── skills/              #   bundled Python skill definitions
├── AgentIntelligence/       # ReAct agent: tool calling, multi-hop reasoning, ai-serve
├── intelligence_eval/       # Eval runner (is-eval)
├── intelligence_ui/         # Launcher dashboard (port 8079)
├── skill_docs/              # Bundled Markdown skill templates
└── practices/               # Bundled best-practice docs for MentorIntelligence
```

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

## License

MIT — see [LICENSE](LICENSE)

---

> See [CHANGELOG.md](CHANGELOG.md) for version history and [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions.
