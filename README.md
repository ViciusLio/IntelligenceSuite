# IntelligenceSuite

> **Retrieve enterprise knowledge in seconds, not hours.**

[![PyPI version](https://img.shields.io/pypi/v/intelligence-suite.svg)](https://pypi.org/project/intelligence-suite/)
[![Python 3.10+](https://img.shields.io/pypi/pyversions/intelligence-suite.svg)](https://pypi.org/project/intelligence-suite/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

A modular RAG suite for **on-premise** environments. Index your codebase and company documents,
then query them in natural language with precise source citations.

```
code + docs  →  parse  →  chunks  →  embed  →  ChromaDB  →  REST API  →  natural-language answers
```

**Zero mandatory cloud. Zero lock-in. On-premise by default** — Ollama for inference, ChromaDB
embedded for storage.

---

## Contents

- [Overview](#overview) — how it works (with diagrams)
- [Quick start](#quick-start) — install, index, serve, query
- [OpenAI-compatible gateway](#openai-compatible-gateway-openwebui--friends) — OpenWebUI, LibreChat, `openai` SDK
- [Installation & extras](#installation--extras)
- [Modules](#modules) — Code · Doc · Mentor · Skill · Agent · Proposal
- **Capabilities**
  - [Intent routing](#intent-routing)
  - [On-demand ingestion (API + UI)](#on-demand-ingestion-api--ui)
  - [Export](#export)
  - [Dependency graph & GraphRAG](#dependency-graph--graphrag)
  - [RAG evaluation (RAGAS)](#rag-evaluation-ragas)
- **Operations**
  - [Multi-project](#multi-project)
  - [Authentication](#authentication)
  - [Observability](#observability)
- [Configuration](#configuration) — `.env` + CLI reference
- [LLM & embedding backends](#llm--embedding-backends)
- [Data model — the chunk](#data-model--the-chunk)
- [Architecture](#architecture)
- [Testing](#testing) · [Troubleshooting](#troubleshooting) · [License](#license)

---

## Overview

IntelligenceSuite is built in **two layers**: a shared engine (`intelligence_core`) that implements
the entire RAG pipeline once, and a set of **domain modules** (Code, Doc, Mentor, Skill, Agent,
Proposal) that reuse that engine and only add domain-specific parsing and an API surface.

Most modules answer questions over your knowledge base via the standard pipeline (steps 1–2).
**ProposalIntelligence** is the exception — it uses the same engine for retrieval but follows a
*style-grounded* flow (step 3) to write answers in your house tone.

### 1 · Ingest — *offline CLI or on-demand API/UI*

Code, documents and team practices are parsed into a **unified chunk schema**, embedded into
vectors, and stored in **per-domain ChromaDB collections**. The same pipeline runs whether it is
driven by the offline CLIs or the opt-in [on-demand routes](#on-demand-ingestion-api--ui) — and
either way indexing is **idempotent** (chunks are re-embedded only when their checksum changed).

```mermaid
flowchart LR
    SRC["💻 Source code"]   --> CLI
    DOC["📄 Documents<br/>PDF·DOCX·XLSX·CSV·MD"] --> CLI
    PRA["📘 Practices"]     --> CLI
    QA["📝 Q&A corpus"]     --> CLI
    DOC --> API
    SRC --> API

    CLI["⌨️ Offline CLI<br/>ci/di/mi/pi-embed"] --> SVC
    API["🌐 On-demand HTTP + UI<br/>/api/v1/ingest/*<br/><i>opt-in IS_INGEST_ENABLED</i>"] --> SVC

    SVC["Parse → unified chunks<br/>checksum idempotency"] --> EMB["Embedder<br/>Ollama · ST · Voyage"]
    EMB --> DB[("ChromaDB<br/>per-domain collections")]

    classDef src fill:#1e3a5f,stroke:#4a90d9,color:#fff;
    classDef proc fill:#2d2d3a,stroke:#7c7c9c,color:#fff;
    classDef store fill:#1f4d3a,stroke:#3fb27f,color:#fff;
    class SRC,DOC,PRA,QA src;
    class CLI,API,SVC,EMB proc;
    class DB store;
```

### 2 · Query — *live, per request*

Every question is **routed**, **retrieved**, **reranked**, optionally **expanded** via the
dependency graph, then **answered** by the LLM with source citations — escalating to Claude only
when local confidence is too low.

```mermaid
flowchart TD
    Q["🧑 User question"] --> IR["🧭 Intent Routing<br/>RAG · SKILL · AGENT"]
    IR --> RET["🔍 Retriever / MultiRetriever<br/>vector search · candidate pool"]
    DB[("ChromaDB")] -.-> RET
    RET --> RR["🎯 Reranker<br/>cross-encoder re-order"]
    RR --> GR["🕸️ GraphRAG<br/>callers + callees"]
    GR --> LLM["🤖 LLM generation<br/>Ollama · OpenAI · vLLM · Claude"]
    LLM --> ESC{"confidence<br/>below threshold?"}
    ESC -->|"yes + Claude key"| CL["☁️ Escalate to Claude"]
    ESC -->|no| ANS["✅ Answer + citations + confidence<br/><i>JSON / streamed over SSE</i>"]
    CL --> ANS

    classDef inp fill:#1e3a5f,stroke:#4a90d9,color:#fff;
    classDef proc fill:#2d2d3a,stroke:#7c7c9c,color:#fff;
    classDef gen fill:#4a2d5f,stroke:#a96fd9,color:#fff;
    classDef out fill:#1f4d3a,stroke:#3fb27f,color:#fff;
    class Q,DB inp;
    class IR,RET,RR,GR proc;
    class LLM,CL gen;
    class ANS out;
```

### 3 · Style-grounded answering — *ProposalIntelligence*

RFPs and vendor questionnaires don't need *facts retrieved* — they need answers written in a
specific **corporate tone**, grounded in how you've answered before. This module embeds the
**question** of each past Q&A pair (not the whole text), so a *new* question matches similar past
ones; the retrieved pairs become **few-shot style exemplars** for the LLM. A `mode` controls how
closely the answer sticks to the corpus.

```mermaid
flowchart LR
    CORP["📝 Past Q&A corpus<br/>table · CSV · XLSX · D:/R:"] --> PP["pi-ingest<br/>1 chunk = 1 Q&A pair"]
    PP --> QEMB["pi-embed<br/><b>embeds the question</b>"]
    QEMB --> QDB[("ChromaDB<br/>proposal_intelligence")]

    NEWQ["🧑 New questionnaire<br/><i>questions only</i>"] --> MATCH["🔍 Match similar<br/>past questions"]
    QDB -.-> MATCH
    MATCH --> FS["🧩 Few-shot style prompt"]
    FS --> MODE{"mode"}
    MODE -->|"anchored"| GEN["🤖 LLM generation<br/>in house style"]
    MODE -->|"commercial"| GEN
    GEN --> OUT["✅ Styled answers + sources<br/>Markdown / web UI / export"]

    classDef src fill:#1e3a5f,stroke:#4a90d9,color:#fff;
    classDef proc fill:#2d2d3a,stroke:#7c7c9c,color:#fff;
    classDef store fill:#1f4d3a,stroke:#3fb27f,color:#fff;
    classDef gen fill:#4a2d5f,stroke:#a96fd9,color:#fff;
    class CORP,NEWQ src;
    class PP,QEMB,MATCH,FS proc;
    class QDB store;
    class GEN,OUT gen;
```

### Operational surface — *ingest & export*

Beyond query, every server exposes two opt-in operational capabilities — index content without
touching the CLI, and download a conversation or answer set as a file.

```mermaid
flowchart TD
    UI["🖥️ Chat / Proposal UI · REST clients"]

    subgraph ING["📥 On-demand ingest — opt-in (IS_INGEST_ENABLED)"]
      direction LR
      IPATH["POST /api/v1/ingest/path<br/><i>inside IS_INGEST_ROOT</i>"]
      IUP["POST /api/v1/ingest/upload<br/><i>[ingest] extra</i>"]
      IJOB["background job<br/>GET /ingest/status/{id}"]
      ISVC["ingestion service<br/>idempotent parse + embed"]
      IPATH --> IJOB
      IUP --> IJOB
      IJOB --> ISVC --> IDB[("ChromaDB")]
    end

    subgraph EXP["⬇️ Export"]
      direction LR
      EREQ["POST /api/v1/export<br/>{format, title, sections}"]
      EREN["renderer"]
      EREQ --> EREN
      EREN --> EMD["Markdown"]
      EREN --> EHTML["HTML"]
      EREN --> EPDF["PDF · <i>[export] extra</i>"]
    end

    UI --> IPATH
    UI --> IUP
    UI --> EREQ

    classDef inp fill:#1e3a5f,stroke:#4a90d9,color:#fff;
    classDef proc fill:#2d2d3a,stroke:#7c7c9c,color:#fff;
    classDef store fill:#1f4d3a,stroke:#3fb27f,color:#fff;
    classDef out fill:#4a2d5f,stroke:#a96fd9,color:#fff;
    class UI inp;
    class IPATH,IUP,IJOB,ISVC,EREQ,EREN proc;
    class IDB store;
    class EMD,EHTML,EPDF out;
```

---

## Quick start

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

Each card has **▶ Start / ■ Stop / Apri →** controls (start, wait for the green dot, then open the
chat UI). The header **▶ Avvia tutto** starts every server at once.

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

> **`ci-embed` is slow the first time** (every chunk is sent to the embedding model). ChromaDB
> persists the result to **`~/.intelligence_suite/chroma`** (absolute path — safe from any working
> directory). Subsequent restarts are **instant**.

### Chat UI

Open any running server's URL — the interface loads instantly:

- Responses **stream word by word** (SSE) · **multi-conversation sidebar** with per-module history
  in localStorage · **source citations** as chips (file · type · score) · live status / chunk count
  / backend
- **Export** the conversation to Markdown / HTML / PDF from the top bar
- **On-demand ingest** panel (when `IS_INGEST_ENABLED`) to index a path or upload files
- Zero extra dependencies — served directly from the RAG server

### Query via REST

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

## OpenAI-compatible gateway (OpenWebUI & friends)

The **gateway** puts a standard OpenAI Chat Completions API in front of the
module servers, so any OpenAI-speaking client — [OpenWebUI](https://openwebui.com),
LibreChat, the `openai` SDK, IDE plugins, `curl` — can use IntelligenceSuite with
**no bespoke integration**. It is a thin protocol adapter: it translates
OpenAI ↔ IntelligenceSuite and proxies over HTTP, forwarding your `Authorization`
header upstream. All retrieval, intent routing, skills, agents and escalation
still happen inside each module server — the gateway holds no retrieval logic.

```bash
gw-serve                              # or: python -m intelligence_gateway.gateway_server
# → http://localhost:8086  (GW_PORT, default 8086)
```

The module servers it fronts must already be running — start them via the
[Launcher](#option-a--launcher-recommended) or individually.

### Models

`GET /v1/models` returns five selectable models:

| Model `id` | Routes to |
|---|---|
| `code-intelligence` | CodeIntelligence (8080) |
| `doc-intelligence` | DocIntelligence (8081) |
| `mentor-intelligence` | MentorIntelligence (8082) |
| `proposal-intelligence` | ProposalIntelligence (8085) |
| `intelligence-suite` | **auto** — a keyword heuristic picks the best module per question |

The module that actually answered is returned in the `X-IS-Module` response
header (handy with the `auto` model). Responses stream token-by-token (SSE) when
the client sets `stream: true` — ProposalIntelligence included.

```bash
curl http://localhost:8086/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "intelligence-suite",
       "messages": [{"role": "user", "content": "Where is authentication handled?"}]}'
```

### Configure OpenWebUI

> **The one gotcha:** add the gateway as an **OpenAI API Connection**, *not* as a
> Tool Server. OpenWebUI's "Tools" expect an OpenAPI spec (`/openapi.json`); the
> gateway is a *model provider*, so adding it under Tools returns 404 / "verify
> failed".

1. OpenWebUI → **Settings → Connections → OpenAI API → Add connection**.
2. **Base URL:** `http://localhost:8086/v1`  (include `/v1`, no trailing slash).
3. **API key:** any non-empty string (e.g. `sk-local`) — unless you enabled
   [authentication](#authentication) on the modules, in which case use that token
   (the gateway forwards it upstream).
4. **Verify** → the five models appear in the model dropdown.
5. Pick a model (or `intelligence-suite` for auto-routing) and chat.

> Run OpenWebUI in its **own** Python environment — it pins many dependencies and
> will downgrade IntelligenceSuite's if installed in the same venv.

---

## Use as an MCP server (Claude Code, Cursor, Claude Desktop)

The suite ships a [Model Context Protocol](https://modelcontextprotocol.io)
server (`is-mcp`) that exposes the knowledge bases as **tools** to any
MCP-compatible client. Unlike the gateway, the LLM lives in the *client* — the
server performs **retrieval only**, so it holds no model keys and never dumps
configuration. It needs no LangChain/LLM dependencies, only the lightweight
`mcp` package.

```bash
pip install "intelligence-suite[mcp]"
```

It exposes the same tools the [ReAct agent](#agentintelligence--multi-hop-react-agent) uses:

| Tool | Backed by | Input |
|---|---|---|
| `search_code` | CodeIntelligence | `query`, `top_k` |
| `search_docs` | DocIntelligence | `query`, `top_k` |
| `search_practices` | MentorIntelligence | `query`, `top_k` |
| `analyze_impact` | Dependency graph (`[graph]`) | `function_name`, `depth` |

Add it to your client's MCP config (Claude Code `.mcp.json`, Cursor, or Claude
Desktop's `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "intelligence-suite": {
      "command": "is-mcp",
      "env": { "IS_PROJECT": "acme" }
    }
  }
}
```

- **Tenancy:** set `IS_PROJECT` to scope the server to one project's collections
  (see [Multi-project](#multi-project)); omit it for the `default` layout.
- **Transport:** stdio (local). The server logs to stderr — stdout is the
  JSON-RPC channel.
- The tools degrade gracefully: if a collection hasn't been indexed yet they
  return an explanatory note instead of failing, so index the relevant module
  first (`ci-embed`, `di-embed`, …).

---

## Installation & extras

```bash
pip install intelligence-suite          # minimal — Ollama for embeddings + generation
pip install "intelligence-suite[all]"   # all core extras (excludes eval/multilang)
pip install -e ".[dev]"                 # development
```

| Extra | Enables |
|---|---|
| `[pdf]` | PDF document parsing (pypdf + pdfplumber) |
| `[ocr]` | OCR for scanned PDFs (requires system `tesseract`) |
| `[docx]` / `[xlsx]` | DOCX / XLSX document parsing |
| `[multilang]` | Tree-sitter parsers for TypeScript, Go, Java, Rust |
| `[graph]` | Dependency graph + GraphRAG context expansion |
| `[ingest]` | Upload route for [on-demand ingestion](#on-demand-ingestion-api--ui) (`python-multipart`) |
| `[export]` | PDF output for [export](#export) (`fpdf2`); Markdown/HTML need no extra |
| `[eval]` | RAGAS evaluation pipeline (`ci-eval`) |
| `[st]` | SentenceTransformer embeddings (CPU-only, offline) |
| `[openai]` / `[claude]` | OpenAI/vLLM/Groq/Mistral · Claude+Voyage backends |
| `[mcp]` | [MCP server](#use-as-an-mcp-server-claude-code-cursor-claude-desktop) (`is-mcp`) — expose tools to Claude Code/Cursor/Claude Desktop |

---

## Modules

| Module | Domain | Description |
|---|---|---|
| `intelligence_core` | Shared layer | Chunk schema, embedder, ChromaDB store, retriever, reranker, escalation, intent routing, ingestion, export, GraphRAG, RAGAS |
| `CodeIntelligence` | Source code | Python AST + Tree-sitter parsers for TS/Go/Java/Rust (regex fallback), YAML, SQL, MD |
| `DocIntelligence` | Company docs | PDF (3-level), DOCX, XLSX, CSV/TSV, TXT/MD ingest pipeline |
| `MentorIntelligence` | Onboarding | Adaptive onboarding — profile detection, sessions, cross-domain path |
| `SkillIntelligence` | Procedures | Step-by-step procedural guidance with cross-domain RAG (code + doc + mentor) |
| `AgentIntelligence` | Multi-hop agent | ReAct agent with tool calling (search_code/docs/practices, analyze_impact) |
| `ProposalIntelligence` | Questionnaires / RFPs | Auto-answers questionnaires in your house style, grounded in past Q&A |

### CodeIntelligence — source code RAG

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

¹ Requires `[multilang]`. Without it, TS/JS and Go fall back to regex parsers automatically.
Tree-sitter parsers also extract `calls` metadata, which powers the dependency graph (`[graph]`).

```bash
ci-parse /path/to/repo               # → chunks.jsonl                  (seconds)
ci-embed                              # → ~/.intelligence_suite/chroma  (slow, one-time)
ci-embed --incremental                # re-embed only new chunks
ci-serve                              # http://localhost:8080
```

### DocIntelligence — document RAG

| Format | Parser | Notes |
|---|---|---|
| **PDF** | pdfplumber → pytesseract → raw binary | 3-level fallback; heading detection via y-coords |
| **DOCX** | python-docx | Heading + body sections |
| **XLSX** | openpyxl | Sheet-by-sheet tabular chunks |
| **CSV / TSV** | Built-in (stdlib `csv`) | Delimiter auto-detected; a schema chunk + a row-preview chunk per file |
| **TXT / MD** | Built-in | Line-based or heading-based split |

```bash
di-ingest /path/to/docs              # → doc_chunks.jsonl              (seconds)
di-embed                              # → ~/.intelligence_suite/chroma  (slow, one-time)
di-serve                              # http://localhost:8081
```

### MentorIntelligence — adaptive onboarding

| Feature | Description |
|---|---|
| **Profile detection** | Infers seniority and specialisation from the intro message |
| **Session management** | Persistent onboarding sessions with full question history |
| **Path builder** | Generates a structured learning path from profile + company practices |
| **Cross-domain orchestrator** | Retrieves from `code`, `doc`, and `mentor` domains in one query |
| **Practice ingestion** | Ingest team conventions, naming guides, runbooks as mentor knowledge |

```bash
mi-ingest ./practices                # ingest best practices (Markdown / TXT / YAML)
mi-serve                              # http://localhost:8082

curl -X POST http://localhost:8082/api/v1/mentor/onboard \
  -H "Content-Type: application/json" \
  -d '{"user_name": "Alice", "intro": "I am a senior Python developer, first day here."}'
```

The repository ships a ready-to-use `practices/` folder documenting IntelligenceSuite itself —
each file is split by `##` headings at ingest time (one chunk per section).

### SkillIntelligence — procedural guidance with RAG

Turns company procedures into interactive step-by-step sessions. Each step retrieves context from
the code/doc/mentor knowledge bases before generating LLM guidance — grounded in your actual
company knowledge.

```bash
si-serve                              # http://localhost:8083
si-ingest ./skill_docs                # load / list Markdown skills

curl -X POST http://localhost:8083/api/v1/skill/start \
  -H "Content-Type: application/json" \
  -d '{"skill_name": "deploy_checklist",
       "parameters": {"service_name": "api", "environment": "staging"}}'
```

Skills are authored in **Markdown** (picked up automatically at server start):

```markdown
# Skill: My Deploy Checklist
> description: Guide the team through a production deploy.
> parameters: service_name (str, required), environment (str, required, enum: staging|production)

## Step 1: Pre-flight checks
**Domini:** doc, code
**Query:** pre-deploy checklist {service_name} {environment}
Verify all CI checks pass and the changelog is updated.
```

…or in **Python** by subclassing `BaseSkill` and dropping the file in `SkillIntelligence/skills/`.

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/skill/list` | GET | List all registered skills |
| `/api/v1/skill/start` | POST | Start a session → first step guidance + sources |
| `/api/v1/skill/next` | POST | Advance to next step (`completed: true` when done) |
| `/api/v1/skill/session/{id}` | GET | Current session metadata |

Sessions are stored as JSON in `~/.intelligence_suite/skill_sessions/`, survive restarts, and are
deleted when all steps complete.

### AgentIntelligence — multi-hop ReAct agent

For questions a single retrieval can't answer ("what breaks if I change function X?"),
AgentIntelligence runs a real **ReAct loop**: reason → call tools → observe → iterate.

| Tool | Purpose |
|---|---|
| `search_code` / `search_docs` / `search_practices` | Semantic search over each domain |
| `analyze_impact` | Walks the reverse call graph — "what depends on this?" (requires `[graph]`) |

```bash
ai-serve                              # http://localhost:8084
curl -X POST http://localhost:8084/api/v1/agent/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What breaks if I change the verify_token function?"}'
```

The agent is also reachable transparently through [Intent Routing](#intent-routing) when a query is
classified as complex multi-domain analysis.

### ProposalIntelligence — answer questionnaires in your house style

Loads a corpus of **past Q&A pairs** (what *and how* you answer), then generates answers to a new
questionnaire that **imitate that style** and stay **grounded in the retrieved examples**.

| Mode | Behaviour |
|---|---|
| `anchored` | Uses **only** facts in the retrieved examples; says so explicitly if they don't cover the question. |
| `commercial` | May elaborate persuasively in the house tone, but specific factual claims stay consistent with the examples — never fabricated. |

In both modes a guardrail forbids inventing named clients, projects, figures or certifications.

```bash
pi-ingest examples/proposal/qa_corpus.md         # → qa_chunks.jsonl
pi-embed                                          # → ChromaDB "proposal_intelligence"
pi-answer examples/proposal/questionnaire.md --mode commercial -o risposte.md
pi-serve                                          # web UI → http://localhost:8085
```

> **Multilingual matching.** Questionnaires are often in Italian — give this module its own embedder
> via per-module override (no need to re-index code/doc):
> ```env
> PI_EMBED_BACKEND=st
> PI_EMBED_MODEL=paraphrase-multilingual-MiniLM-L12-v2
> ```

> **Privacy.** Real corpora can contain confidential bid data, so `qa_corpus/`, `questionari/`,
> `qa_chunks.jsonl` and `risposte.md` are git-ignored. Only the **synthetic** demo under
> `examples/proposal/` is versioned.

---

## Intent routing

Every `/api/v1/query` request is transparently classified before being answered — the user writes
in the chat as always; the routing is invisible.

| Level | When | Result |
|---|---|---|
| **RAG** | Simple factual question | Standard retrieval + LLM answer |
| **SKILL** | Procedural request ("guide me", "step by step") | SkillSession started, first step returned |
| **AGENT** | Complex multi-domain analysis | ReAct agent (enable with `INTENT_AGENT_ENABLED=true`) |

**Two-stage classification:** a 0 ms keyword heuristic handles confident cases; an LLM call
(~300 ms) is made only for ambiguous ones (confidence < 0.85). Any failure silently falls back to
RAG. Disable entirely with `INTENT_ROUTING=false`.

---

## On-demand ingestion (API + UI)

Besides the offline `ci-embed` / `di-embed` / `pi-embed` CLIs, content can be indexed **on demand**
over HTTP and straight from the chat UI. Opt-in and **off by default** — when disabled the routes
return `404` and behaviour is identical to before.

```env
IS_INGEST_ENABLED=true            # default false → routes absent (404), no UI panel
IS_INGEST_ROOT=/srv/knowledge     # server-side root the path endpoint is confined to
IS_INGEST_MAX_MB=50               # per-file upload cap (413 on overflow)
```

The same parse+embed pipeline runs, so indexing stays **idempotent**: chunks are keyed by the
deterministic `domain::type::locator` ID and re-embedded only when their checksum changed; on a
full path scan, orphaned chunks are pruned. The heavy work always runs in a **background thread**,
so the HTTP call returns at once with a `job_id` to poll.

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/ingest/path` | POST | Index a server-side path (validated **inside** `IS_INGEST_ROOT`). Body `{path, module?, incremental?}` → `{job_id, status}`. |
| `/api/v1/ingest/upload` | POST | Index uploaded files (multipart). Per-file cap `IS_INGEST_MAX_MB`. Needs the `[ingest]` extra; absent → route not mounted. |
| `/api/v1/ingest/status/{job_id}` | GET | Poll a job (`queued` → `running` → `done`/`error`); `404` if unknown. |

Each request targets the hosting server's module by default; an optional `module` field can
retarget to any of `code | doc | mentor | proposal`. `/health` reports `ingest_enabled` so the chat
UI shows a **"📥 Indicizza contenuti"** panel (server-side path for Code, file upload for the
others) that submits the job and live-polls its status. All routes sit behind the same Bearer
[auth](#authentication) middleware.

```bash
curl -X POST http://localhost:8081/api/v1/ingest/upload \
     -F "files=@./report.csv" -F "files=@./spec.pdf"
# → {"job_id":"…","status":"queued","module":"doc","files":2}

curl http://localhost:8081/api/v1/ingest/status/<job_id>
# → {"status":"done","stats":{"new":2,"skipped":0,"deleted":0, …}}
```

---

## Export

Turn a chat conversation or a set of Proposal answers into a **downloadable file** —
`POST /api/v1/export`, mounted on every module server. Markdown and a standalone HTML page are
stdlib (always available); **PDF** needs the opt-in `[export]` extra (`fpdf2`).

| `format` | Extra | Output |
|---|---|---|
| `markdown` | *(none)* | `text/markdown` — title + `##` sections + `_Fonti: …_` |
| `html` | *(none)* | standalone, escaped `text/html` page |
| `pdf` | `[export]` | `application/pdf` (via `fpdf2`); `503` if the extra is missing |

```bash
curl -X POST http://localhost:8080/api/v1/export \
  -H "Content-Type: application/json" \
  -d '{"format":"markdown","title":"Conversazione",
       "sections":[{"heading":"Tu","body":"Where is auth handled?"},
                   {"heading":"Assistant","body":"In auth/jwt.py …",
                    "sources":[{"source":"auth/jwt.py"}]}]}' \
  -o conversazione.md
```

The response is an attachment (`Content-Disposition`) with the right `Content-Type`. An unknown
`format` → `400`; `format=pdf` without the extra → `503` (Markdown/HTML keep working). In the UI an
**"⬇︎ Esporta"** menu appears in the chat top bar (active conversation) and the Proposal header
(generated answers).

---

## Dependency graph & GraphRAG

CodeIntelligence chunks carry `calls` / `imports` / `bases` metadata. The `[graph]` extra builds a
directed dependency graph with NetworkX, persisted to `~/.intelligence_suite/graph/`.

```bash
pip install "intelligence-suite[graph]"
ci-graph --stats                 # build the graph and print node/edge stats
ci-graph --top-critical 10       # the 10 most-called functions (impact hotspots)
```

Once the graph exists the retriever automatically performs **GraphRAG**: after the semantic search
it expands context with structurally-related nodes (callers + callees) of the top hits. Fully
optional and non-breaking — if the graph is missing or fails, retrieval proceeds unchanged.

---

## RAG evaluation (RAGAS)

Measure retrieval/answer quality on four dimensions: faithfulness, answer relevancy, context
precision, context recall.

```bash
pip install "intelligence-suite[eval]"
ci-eval --domain code --samples 50          # generate testset, run, score
ci-eval --domain doc --regenerate           # force-regenerate the cached testset
```

KPI targets: faithfulness ≥ 0.75, answer_relevancy ≥ 0.75, context_precision ≥ 0.70,
context_recall ≥ 0.68. Reports are saved under `~/.intelligence_suite/eval/` with a delta vs the
previous run; the command exits non-zero if any target is missed (CI-friendly).

---

## Multi-project

Run several isolated knowledge bases from one installation. Set `IS_PROJECT` to namespace **every**
ChromaDB collection and state directory by project.

```env
IS_PROJECT=acme    # default "default" → identical to the single-project layout
```

| Concern | `IS_PROJECT` unset (`default`) | `IS_PROJECT=acme` |
|---|---|---|
| Collections | `code_intelligence`, `doc_intelligence`, … | `acme_code_intelligence`, … |
| State dirs | `~/.intelligence_suite/<chroma\|graph\|eval\|skill_sessions>/` | `~/.intelligence_suite/acme/…` |

Names and paths are resolved at call time by `intelligence_core/paths.py` (single source of truth);
nothing leaks between projects. The default value reproduces the pre-multi-project layout, so
existing installs keep working with **zero migration**.

---

## Authentication

Optional Bearer-token auth across **all** servers. Disabled by default. Enable it to require a
shared API key on every `/api/v1/*` endpoint.

```env
IS_AUTH_ENABLED=true                 # default false
IS_API_KEY=your-long-random-secret   # required when auth is enabled
```

```bash
curl -H "Authorization: Bearer your-long-random-secret" \
     -X POST http://localhost:8080/api/v1/query -d '{"question":"how does retrieval work?"}'
```

- **Public paths** stay open: `/` (UI), `/health`, `/docs`, `/redoc`, `/openapi.json`.
- A missing/wrong token on a protected path → **HTTP 403** `{"error":"invalid_api_key"}`.
- If `IS_AUTH_ENABLED=true` but `IS_API_KEY` is empty, the server **refuses to start**.
- The middleware is pure ASGI, so **SSE streaming is never buffered or broken**.

---

## Observability

Structured logging and in-memory metrics, **stdlib only** — opt-in, zero impact on defaults.

```env
IS_LOG_LEVEL=INFO     # DEBUG | INFO | WARNING | ERROR   (default INFO)
IS_LOG_FORMAT=json    # json (default) | text            (text = dev-friendly)
IS_METRICS_ENABLED=true   # default false → GET /metrics returns 404
```

One `query` event is emitted per `/api/v1/query` **and** `/api/v1/stream` call, and one `ingestion`
event per embed run. **Question/answer text is never logged** — only metadata (e.g. question
*length*).

```bash
curl http://localhost:8080/metrics
# {"queries_total":128,"queries_escalated":7,"avg_latency_ms":142.6,"avg_confidence":0.78,"uptime_seconds":3601.2}
```

Counters are in-memory and thread-safe; they reset on restart. The endpoint is registered on all
six servers.

---

## Configuration

Copy `.env.example` to `.env` and edit. All variables are also accepted as plain environment
variables — no `.env` file required in CI/CD.

```env
# LLM generation (ollama | openai | vllm | claude)
LLM_BACKEND=ollama
OLLAMA_MODEL=qwen2.5-coder:7b
# OPENAI_API_KEY / OPENAI_MODEL / OPENAI_BASE_URL   # OpenAI-compatible servers
# ANTHROPIC_API_KEY / CLAUDE_MODEL                  # Claude

# Embeddings (ollama | st | claude)
EMBED_BACKEND=ollama
OLLAMA_EMBED_MODEL=nomic-embed-text

# Vector store — default ~/.intelligence_suite/chroma (absolute, CWD-independent)
VECTOR_STORE=chromadb
# CHROMA_PERSIST_DIR=/custom/path/chroma

# Escalation: fall back to Claude when confidence < threshold
ESCALATION_THRESHOLD=0.70

# Intent routing
INTENT_ROUTING=true
INTENT_AGENT_ENABLED=true

# On-demand ingestion (opt-in)
# IS_INGEST_ENABLED=false
# IS_INGEST_ROOT=
# IS_INGEST_MAX_MB=50

# Server ports — all run simultaneously
CI_PORT=8080   DI_PORT=8081   MI_PORT=8082   SI_PORT=8083   AGENT_PORT=8084   PI_PORT=8085
```

Per-module LLM/embedder overrides (`CI_LLM_*`, `DI_LLM_*`, `MI_LLM_*`, `PI_EMBED_*`, …) let each
domain use a different backend; leave empty to inherit the global settings.

### CLI reference

| Command | Module | Action |
|---|---|---|
| `ci-parse <repo>` / `ci-embed [file]` / `ci-serve` | CodeIntelligence | Parse → embed → serve (port 8080) |
| `di-ingest <dir>` / `di-embed [file]` / `di-serve` | DocIntelligence | Ingest → embed → serve (8081) |
| `mi-ingest <dir>` / `mi-serve` | MentorIntelligence | Ingest practices → serve (8082) |
| `si-ingest <dir>` / `si-serve` | SkillIntelligence | Load skills → serve (8083) |
| `ai-serve` | AgentIntelligence | ReAct agent server (8084) |
| `pi-ingest <corpus>` / `pi-embed [file]` / `pi-answer <q>` / `pi-serve` | ProposalIntelligence | Ingest → embed → answer → serve (8085) |
| `ci-eval` | intelligence_core | RAGAS evaluation (`--domain code\|doc\|mentor\|all`, requires `[eval]`) |
| `ci-graph` | intelligence_core | Build dependency graph + stats (requires `[graph]`) |
| `is-launch` | Launcher | Start/stop/monitor all modules — port 8079 |

---

## LLM & embedding backends

### Generation

| Backend | `LLM_BACKEND` | Extra | Notes |
|---|---|---|---|
| **Ollama** | `ollama` | *(none)* | Default — fully local, no API key, no GPU |
| **OpenAI** | `openai` | `[openai]` | GPT-4o, GPT-4o-mini, o1, … |
| **vLLM / LM Studio** | `vllm` | `[openai]` | Local OpenAI-compatible server; set `OPENAI_BASE_URL` |
| **Groq / Mistral** | `openai` | `[openai]` | Set `OPENAI_BASE_URL` to the provider endpoint |
| **Claude** | `claude` | `[claude]` | Anthropic claude-opus / claude-sonnet … |

Switch backend with a single env var. Each module can use a different one via `CI_LLM_*`,
`DI_LLM_*`, `MI_LLM_*`. When confidence < `ESCALATION_THRESHOLD` and `ANTHROPIC_API_KEY` is set, the
answer is **escalated to Claude** regardless of the primary backend.

### Embedding

| Backend | `EMBED_BACKEND` | Extra | Notes |
|---|---|---|---|
| **Ollama** | `ollama` | *(none)* | Default — fully local |
| **SentenceTransformer** | `st` | `[st]` | CPU-only, fully offline |
| **Claude / Voyage** | `claude` | `[claude]` | Cloud embeddings via Voyage AI |

For non-English content, use a multilingual SentenceTransformer model
(`paraphrase-multilingual-MiniLM-L12-v2`, 50+ languages).

> **Switching embedding model requires re-indexing from scratch** — vector dimensions may change
> (384 → 768) and ChromaDB rejects mixed-dimension collections. Delete the data dir first:
> ```bash
> rm -rf ~/.intelligence_suite/chroma                              # Linux / macOS
> Remove-Item -Recurse -Force "$HOME\.intelligence_suite\chroma"   # Windows PowerShell
> ```

ChromaDB runs **embedded** — no server or Docker. Override the path with `CHROMA_PERSIST_DIR`.

---

## Data model — the chunk

Every source file and document is converted into self-contained **semantic chunks** with a unified
schema and a deterministic `domain::type::locator` ID (so re-indexing is idempotent):

```json
{
  "id":       "code::function::myrepo.auth.jwt.verify_token",
  "domain":   "code",
  "type":     "function",
  "text":     "### verify_token\n\n```python\ndef verify_token(token: str) -> dict:\n    ...\n```",
  "source":   "auth/jwt.py",
  "language": "python",
  "metadata": { "name": "verify_token", "line_start": 42, "line_end": 67,
                "calls": ["jwt.decode"], "imports": ["jwt"] }
}
```

| Domain | Types |
|---|---|
| `code` | `function`, `class`, `interface`, `config_block`, `module`, `file` |
| `doc` | `section`, `table`, `paragraph` |
| `mentor` | `practice`, `onboarding_step`, `role_guide`, `faq`, `glossary` |

---

## Architecture

### The engine — `intelligence_core`

Every module delegates to these shared components, so a fix here benefits all domains at once:

| Component | File | What it does |
|---|---|---|
| **Chunk schema** | `chunk.py` | Universal unit of knowledge; deterministic `domain::type::locator` ID |
| **Embedder** | `embedder.py` | Pluggable text→vector (Ollama/ST/Voyage); **fails loudly** if unreachable |
| **Vector store** | `store.py` | ChromaDB embedded; one collection per domain |
| **Retriever / MultiRetriever** | `retriever.py` | Candidate pool → rerank → optional GraphRAG; multi-collection for cross-domain |
| **Reranker** | `reranker.py` | Cross-encoder re-scoring, sigmoid-normalised, opt-in via `RERANK_ENABLED` |
| **LLM provider** | `llm/` | Provider-agnostic generation; per-module overrides |
| **Intent routing** | `intent.py` | RAG / SKILL / AGENT classification; falls back to RAG on any failure |
| **Ingestion** | `ingestion.py`, `ingest_api.py` | On-demand idempotent parse+embed service + opt-in HTTP routes |
| **Export** | `export.py`, `export_api.py` | Markdown/HTML/PDF renderers + `POST /api/v1/export` |
| **GraphRAG** | `graph/` | NetworkX dependency graph + context expansion |
| **Evaluation** | `evaluation/` | RAGAS pipeline behind `ci-eval` |

### Request lifecycle (a single `/api/v1/query`)

1. **Route** — Intent Routing classifies (RAG / SKILL / AGENT).
2. **Retrieve** — embed the question, pull a candidate pool from ChromaDB.
3. **Rerank** — cross-encoder re-orders candidates, cut to `top_k`.
4. **Expand** *(optional)* — GraphRAG adds structurally-related code.
5. **Generate** — the chosen LLM writes an answer grounded in the chunks.
6. **Escalate** *(conditional)* — below threshold + Claude key → regenerate via cloud.
7. **Respond** — answer + source citations + confidence + backend, streamed over SSE.

### Source tree

```
IntelligenceSuite/
├── intelligence_core/       # Shared engine (chunk, embedder, store, retriever, reranker,
│   ├── parsers/             #   intent, ingestion, export, graph, evaluation, llm/)
│   ├── llm/  graph/  evaluation/
├── CodeIntelligence/        # Code RAG: Python AST + Tree-sitter/regex, YAML, SQL, MD
├── DocIntelligence/         # Doc RAG: PDF (3-level), DOCX, XLSX, CSV, TXT
├── MentorIntelligence/      # Adaptive onboarding
├── SkillIntelligence/       # Procedural guidance (skills/)
├── AgentIntelligence/       # ReAct agent
├── ProposalIntelligence/    # Questionnaire/RFP auto-answer + web UI
├── intelligence_gateway/    # OpenAI-compatible adapter (gw-serve, port 8086)
├── intelligence_eval/       # Eval runner (is-eval)
├── intelligence_ui/         # Launcher dashboard (port 8079)
├── skill_docs/              # Bundled Markdown skill templates
└── practices/               # Bundled best-practice docs for MentorIntelligence
```

### Design principles

| Principle | Implementation |
|---|---|
| **On-premise first** | Ollama + ChromaDB by default — no cloud required |
| **Domain-aware chunking** | Every chunk carries `domain` — prevents cross-contamination |
| **Deterministic IDs** | `domain::type::locator` — safe to re-index, dedup-friendly |
| **Fail-safe ingestion** | One broken file never crashes the pipeline |
| **Fail-loud embedding** | Embedder raises if unreachable — never stores zero-vectors |
| **Non-breaking extras** | Tree-sitter, graph, eval, ingest, export are opt-in; absence degrades gracefully |

---

## Testing

```bash
pip install -e ".[dev]"
pytest -m "not slow"       # everything except tests needing a real backend
pytest -m kpi              # only the deterministic retrieval-quality tests
```

The suite runs **offline and deterministically** — no Ollama, no network, no optional extra, no
disk state required. **KPI tests run in CI** (they no longer skip): they mount a disk-less,
in-memory ChromaDB loaded with versioned synthetic fixtures and assert Hit@1 / Hit@5 / MRR on known
chunks. `ci-eval` (RAGAS) needs a live LLM + populated store, so it stays out of standard CI — see
[`CI.md`](CI.md).

---

## Troubleshooting

- **CLI scripts not found after install (Windows)** — pip installs them in a user `Scripts` folder
  that may not be on `PATH`. Add it, or run modules directly: `python -m CodeIntelligence.rag_server`.
- **Ollama not reachable during embedding** — `ci-embed`/`di-embed` **fail loudly** (no silent
  zero-vectors). Start Ollama (`ollama serve && ollama pull nomic-embed-text`) or set
  `EMBED_BACKEND=st` (offline, no server).
- **ChromaDB DuplicateIDError on embed** — `chunks.jsonl` has duplicate IDs, usually because
  `build/lib/` got indexed. `rm -rf build/ dist/ ~/.intelligence_suite/chroma` and re-run.
  `parse_repo` excludes `build/`, `dist/`, `venv/` automatically.

---

## License

MIT — see [LICENSE](LICENSE).

> See [CHANGELOG.md](CHANGELOG.md) for version history and [ARCHITECTURE.md](ARCHITECTURE.md) for
> design decisions.
