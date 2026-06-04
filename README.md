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

## How it works

IntelligenceSuite is built in **two layers**: a shared engine (`intelligence_core`) that
implements the entire RAG pipeline once, and a set of **domain modules** (Code, Doc, Mentor,
Skill, Agent, Proposal) that reuse that engine and only add domain-specific parsing and an API
surface. Everything runs **on-premise by default** — Ollama for inference, ChromaDB embedded for
storage.

Most modules answer questions over your knowledge base via the standard pipeline (steps 1–2 below).
**ProposalIntelligence** is the exception — it uses the same engine for retrieval but follows a
*style-grounded* flow (step 3) to write answers in your house tone.

### 1 · Ingest — *one-time, offline*

Your code, documents and team practices are parsed into a **unified chunk schema**, embedded into
vectors, and stored in **per-domain ChromaDB collections**.

```mermaid
flowchart LR
    SRC["💻 Source code"]   --> P1["Parser<br/>AST · Tree-sitter · regex"]
    DOC["📄 Documents"]     --> P2["Parser<br/>PDF · DOCX · XLSX · CSV · MD"]
    PRA["📘 Practices"]     --> P3["Ingest<br/>Markdown sections"]
    P1 --> CH["chunks.jsonl<br/><i>unified schema</i>"]
    P2 --> CH
    P3 --> CH
    CH --> EMB["Embedder<br/>Ollama · ST · Voyage"]
    EMB --> DB[("ChromaDB<br/>per-domain collections")]

    classDef src fill:#1e3a5f,stroke:#4a90d9,color:#fff;
    classDef proc fill:#2d2d3a,stroke:#7c7c9c,color:#fff;
    classDef store fill:#1f4d3a,stroke:#3fb27f,color:#fff;
    class SRC,DOC,PRA src;
    class P1,P2,P3,CH,EMB proc;
    class DB store;
```

> Besides the offline CLIs, the same parse+embed pipeline is also exposed **on demand** over
> HTTP and from the chat UI — opt-in via `IS_INGEST_ENABLED`. See
> [On-demand ingestion](#on-demand-ingestion--api--ui) below.

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
    ESC -->|no| ANS["✅ Answer + source citations + confidence<br/><i>JSON / streamed over SSE</i>"]
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
specific **corporate tone**, grounded in how you've answered before. So this module embeds the
**question** of each past Q&A pair (not the whole text), so a *new* question — even if phrased
differently — matches similar past ones; the retrieved pairs then become **few-shot style
exemplars** for the LLM. A selectable `mode` controls how closely the answer sticks to the corpus.

```mermaid
flowchart LR
    CORP["📝 Past Q&A corpus<br/>table · CSV · XLSX · D:/R:"] --> PP["pi-ingest<br/>1 chunk = 1 Q&A pair"]
    PP --> QEMB["pi-embed<br/><b>embeds the question</b>"]
    QEMB --> QDB[("ChromaDB<br/>proposal_intelligence")]

    NEWQ["🧑 New questionnaire<br/><i>questions only</i>"] --> MATCH["🔍 Match similar<br/>past questions"]
    QDB -.-> MATCH
    MATCH --> FS["🧩 Few-shot style prompt<br/>retrieved Q&A as exemplars"]
    FS --> MODE{"mode"}
    MODE -->|"anchored"| GEN["🤖 LLM generation<br/>in house style"]
    MODE -->|"commercial"| GEN
    GEN --> OUT["✅ Styled answers<br/>+ style sources · Markdown / web UI"]

    classDef src fill:#1e3a5f,stroke:#4a90d9,color:#fff;
    classDef proc fill:#2d2d3a,stroke:#7c7c9c,color:#fff;
    classDef store fill:#1f4d3a,stroke:#3fb27f,color:#fff;
    classDef gen fill:#4a2d5f,stroke:#a96fd9,color:#fff;
    classDef out fill:#1f4d3a,stroke:#3fb27f,color:#fff;
    class CORP,NEWQ src;
    class PP,QEMB,MATCH,FS proc;
    class QDB store;
    class GEN gen;
    class OUT out;
```

A more detailed per-component breakdown lives in [Architecture](#architecture) below; the full
ProposalIntelligence walkthrough is [here](#proposalintelligence--auto-answer-questionnaires-in-your-house-style).

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
- **Export** the conversation to Markdown / HTML / PDF from the top bar
- **On-demand ingest** panel (when `IS_INGEST_ENABLED`) to index a path or upload files
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
| `DocIntelligence` | Company docs | PDF (3-level), DOCX, XLSX, CSV/TSV, TXT ingest pipeline |
| `MentorIntelligence` | Onboarding | Adaptive onboarding — profile detection, sessions, cross-domain path |
| `SkillIntelligence` | Procedures | Step-by-step procedural guidance with cross-domain RAG (code + doc + mentor) |
| `AgentIntelligence` | Multi-hop agent | ReAct agent with tool calling (search_code/docs/practices, analyze_impact) |
| `ProposalIntelligence` | Questionnaires / RFPs | Auto-answers questionnaires in your house style, grounded in a corpus of past Q&A |

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

# On-demand ingest uploads (POST /api/v1/ingest/upload)
pip install "intelligence-suite[ingest]"

# Export to PDF (POST /api/v1/export?format=pdf) — Markdown/HTML need no extra
pip install "intelligence-suite[export]"

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
| **CSV / TSV** | Built-in (stdlib `csv`) | Delimiter auto-detected; a schema chunk + a row-preview chunk per file |
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

## ProposalIntelligence — auto-answer questionnaires in your house style

Answering RFPs, tenders and vendor questionnaires is repetitive: the same kinds of questions come
back, and the answers must follow a specific corporate tone (a flat *"no"* is never the answer).
ProposalIntelligence loads a corpus of **past Q&A pairs** — which capture both *what* you answer and
*how* — then, given a new questionnaire, generates answers that **imitate that style** and stay
**grounded in the retrieved examples**.

```
Q&A corpus (table / CSV / XLSX / D:·R: markers)
        ↓  pi-ingest          → 1 chunk = 1 Q&A pair
        ↓  pi-embed           → embed the QUESTION → ChromaDB "proposal_intelligence"
new questionnaire (questions only)
        ↓  pi-answer          → retrieve similar past Q&A → few-shot style prompt → LLM
        ↓
risposte.md  (one styled answer per question + the style sources used)
```

**Two answer modes** (`--mode`):

| Mode | Behaviour |
|---|---|
| `anchored` | Uses **only** facts present in the retrieved examples. If they don't cover the question, it says so explicitly instead of inventing. |
| `commercial` | May elaborate persuasively in the house tone, but specific factual claims (clients, projects, numbers, certifications) stay consistent with the examples — never fabricated. |

In both modes a guardrail forbids inventing named clients, projects, figures or certifications.

### CLI quickstart

```bash
# 1. Load a corpus of past answers (synthetic demo included)
pi-ingest examples/proposal/qa_corpus.md         # → qa_chunks.jsonl
pi-embed                                          # → ChromaDB "proposal_intelligence"

# 2. Answer a new questionnaire in the company style
pi-answer examples/proposal/questionnaire.md --mode commercial -o risposte.md

# 3. Or serve it — opens a web UI at http://localhost:8085 (also reachable from the launcher)
pi-serve
curl -X POST http://localhost:8085/api/v1/proposal/answer \
  -H "Content-Type: application/json" \
  -d '{"questions": ["Do you have cloud migration experience?"], "mode": "anchored"}'
```

The `pi-serve` web UI lets you paste a questionnaire, pick the mode and see the styled answers (with
their style sources) — and it shows up as a card in the **launcher** alongside the other modules.

> **Multilingual matching.** Since questionnaires are often in Italian, give this module its own
> embedder via the per-module override — no need to re-index the code/doc collections:
> ```env
> PI_EMBED_BACKEND=st
> PI_EMBED_MODEL=paraphrase-multilingual-MiniLM-L12-v2
> ```

> **Privacy.** Real corpora and questionnaires can contain confidential bid data, so `qa_corpus/`,
> `questionari/`, `qa_chunks.jsonl` and `risposte.md` are git-ignored. Only the **synthetic** demo
> under `examples/proposal/` is versioned.

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

# Reranking — cross-encoder re-ordering before top_k (boosts context precision)
# Opt-in, requires the [st] extra. Downloads RERANK_MODEL once on first use.
# RERANK_ENABLED=true
# RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
# RERANK_CANDIDATES=30

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
| `pi-ingest <corpus>` | ProposalIntelligence | Ingest a Q&A corpus (table/CSV/XLSX or `D:`/`R:` markers) → `qa_chunks.jsonl` |
| `pi-embed [file]` | ProposalIntelligence | Embed Q&A pairs (on the question) into ChromaDB `proposal_intelligence` |
| `pi-answer <questions>` | ProposalIntelligence | Auto-answer a questionnaire in house style → Markdown (`--mode anchored\|commercial`) |
| `pi-serve` | ProposalIntelligence | Start the proposal server + web UI on `PI_PORT` (default 8085) |
| `ci-eval` | intelligence_core | Run the RAGAS evaluation pipeline — `--domain code\|doc\|mentor\|all` (requires `[eval]`) |
| `ci-graph` | intelligence_core | Build the dependency graph + stats (requires `[graph]`) |
| `is-launch` | Launcher | Dashboard to start/stop/monitor all modules — port 8079 |

---

## Multi-project support

Run several isolated knowledge bases from one installation. Set `IS_PROJECT` to
namespace **every** ChromaDB collection and state directory by project — useful
to keep separate clients, teams, or environments apart on the same machine.

```env
IS_PROJECT=acme    # default "default" → identical to the v0.8.x layout
```

| Concern | `IS_PROJECT` unset (`default`) | `IS_PROJECT=acme` |
|---|---|---|
| ChromaDB collections | `code_intelligence`, `doc_intelligence`, … | `acme_code_intelligence`, `acme_doc_intelligence`, … |
| State directories | `~/.intelligence_suite/<chroma\|graph\|eval\|skill_sessions>/` | `~/.intelligence_suite/acme/<chroma\|graph\|eval\|skill_sessions>/` |

Collection names and paths are resolved at call time by
`intelligence_core/paths.py` (single source of truth). Switching projects is just
a matter of changing `IS_PROJECT` and re-running the ingest commands — nothing
leaks between projects. The default value reproduces the exact pre-0.9.0 layout,
so existing installs keep working with **zero migration**.

---

## Authentication

Optional Bearer-token auth across **all** servers. Disabled by default → behaves
exactly like v0.8.x. Enable it to require a shared API key on every `/api/v1/*`
endpoint.

```env
IS_AUTH_ENABLED=true                 # default false
IS_API_KEY=your-long-random-secret   # required when auth is enabled
```

```bash
# With auth enabled, protected calls need the header:
curl -H "Authorization: Bearer your-long-random-secret" \
     -X POST http://localhost:8080/api/v1/query \
     -d '{"question":"how does retrieval work?"}'
```

- **Public paths** stay open without a token: `/` (UI), `/health` (launcher
  poller), `/docs`, `/redoc`, `/openapi.json`.
- A missing or wrong token on a protected path → **HTTP 403** with body
  `{"error":"invalid_api_key"}`.
- If `IS_AUTH_ENABLED=true` but `IS_API_KEY` is empty, the server **refuses to
  start** (`AuthConfigError`) instead of silently rejecting every request.
- The middleware is pure ASGI, so **SSE streaming is never buffered or broken**.
- For inter-module calls, `intelligence_core.auth.auth_headers()` returns the
  right `Authorization` header (empty dict when auth is off), so callers work
  the same regardless of configuration.

---

## Observability

Structured logging and in-memory metrics, **stdlib only** — no extra dependency,
opt-in, zero impact on the default behaviour.

### Structured logging

The suite logs **one JSON object per line to stdout** by default — ready to ship
to any log collector (Loki, ELK, CloudWatch, …). Switch to a human-readable
format for local development.

```env
IS_LOG_LEVEL=INFO     # DEBUG | INFO | WARNING | ERROR   (default INFO)
IS_LOG_FORMAT=json    # json (default) | text            (text = dev-friendly)
```

One `query` event is emitted per `/api/v1/query` **and** `/api/v1/stream` call
(streaming events fire once the response is fully sent), and one `ingestion`
event at the end of each embed run (`ci-embed`, `di-embed`, `pi-embed`). Example:

```json
{"ts":"2026-06-04T10:12:03Z","level":"INFO","logger":"intelligence_suite","msg":"query","event":"query","module":"code","project":"default","intent":"rag","question_length":42,"top_k":5,"confidence":0.81,"escalated":false,"backend":"ollama","latency_ms":128.4}
```

> **Privacy by design:** the text of questions and answers is **never** logged —
> only metadata such as the question *length*. Bodies are potentially sensitive.

### Metrics endpoint

Opt-in per-process counters, exposed as JSON. Disabled by default: when off the
route does not exist (`404`).

```env
IS_METRICS_ENABLED=true   # default false → GET /metrics returns 404
```

```bash
curl http://localhost:8080/metrics
{
  "queries_total": 128,
  "queries_escalated": 7,
  "avg_latency_ms": 142.6,
  "avg_confidence": 0.78,
  "uptime_seconds": 3601.2
}
```

Counters are in-memory and thread-safe; they reset when the process restarts.
The endpoint is registered on all six servers.

---

## On-demand ingestion — API + UI

Besides the offline `ci-embed` / `di-embed` / `pi-embed` CLIs, content can be indexed
**on demand** over HTTP and straight from the chat UI. Opt-in and **off by default** — when
disabled the routes return `404` and behaviour is identical to before.

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
| `/api/v1/ingest/status/{job_id}` | GET | Poll a job's status/stats (`queued` → `running` → `done`/`error`); `404` if unknown. |

Each request targets the hosting server's module by default; an optional `module` field can
retarget to any of `code | doc | mentor | proposal`. `/health` reports `ingest_enabled` so the
chat UI can show a **"📥 Indicizza contenuti"** panel (server-side path for Code, file upload for
Doc/Mentor/Proposal) that submits the job and live-polls its status. All routes sit behind the
same Bearer auth middleware as the rest of the API.

```bash
curl -H "Content-Type: application/json" \
     -X POST http://localhost:8081/api/v1/ingest/upload \
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

```bash
curl -X POST http://localhost:8080/api/v1/export \
  -H "Content-Type: application/json" \
  -d '{"format":"markdown","title":"Conversazione",
       "sections":[{"heading":"Tu","body":"Where is auth handled?"},
                   {"heading":"Assistant","body":"In auth/jwt.py …",
                    "sources":[{"source":"auth/jwt.py"}]}]}' \
  -o conversazione.md
```

The response is returned as an attachment (`Content-Disposition`) with the right `Content-Type`.
An unknown `format` → `400`; `format=pdf` without the extra → `503`, while Markdown/HTML keep
working. In the UI an **"⬇︎ Esporta"** menu (Markdown / HTML / PDF) appears in the chat top bar
(exports the active conversation) and in the Proposal header (exports the generated answers).

| `format` | Extra | Output |
|---|---|---|
| `markdown` | *(none)* | `text/markdown` — title + `##` sections + `_Fonti: …_` |
| `html` | *(none)* | standalone, escaped `text/html` page |
| `pdf` | `[export]` | `application/pdf` (via `fpdf2`); `503` if the extra is missing |

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
```

The suite runs **offline and deterministically** — no Ollama, no network, no
optional extra, no disk state required.

**Retrieval-quality (KPI) tests run in CI**, they no longer skip. They mount a
disk-less, in-memory ChromaDB loaded with versioned synthetic fixtures
(`tests/fixtures/`) and assert Hit@1 / Hit@5 / MRR on known chunks, so a broken
retriever fails the build for real.

Two pytest markers (declared in `pyproject.toml`) let you slice the suite:

```bash
pytest -m kpi              # only the deterministic retrieval-quality tests
pytest -m "not slow"       # everything except tests needing a real backend
```

| Marker | Meaning |
|---|---|
| `kpi` | Retrieval quality on an in-memory store. Runs in CI, never skips. |
| `slow` | Needs a real embedding backend (Ollama / sentence-transformers) or network. |

`ci-eval` (RAGAS) needs a live LLM **and** a populated store, so it stays out of
standard CI. See [`CI.md`](CI.md) for the full reference.

---

## Architecture

A component-level reference for the pipeline shown in [How it works](#how-it-works) above.

### The engine — `intelligence_core`

Every module delegates to these shared components, so a fix or improvement here benefits all
five domains at once:

| Component | File | What it does and why it matters |
|---|---|---|
| **Chunk schema** | `chunk.py` | The universal unit of knowledge. A self-contained snippet (`id`, `domain`, `type`, `text`, `source`, `metadata`) with a deterministic `domain::type::locator` ID so re-indexing is idempotent. Everything in the suite speaks "chunks". |
| **Embedder** | `embedder.py` | Turns chunk text into vectors. Pluggable backend (Ollama / SentenceTransformer / Voyage) behind one interface. **Fails loudly** if the model is unreachable — never stores zero-vectors that would silently poison search. |
| **Vector store** | `store.py` | Thin wrapper over **ChromaDB embedded** (no server, no Docker). One collection per domain (`code_intelligence`, `doc_intelligence`, `mentor_intelligence`) keeps domains from contaminating each other's results. |
| **Retriever** | `retriever.py` | The query workhorse. Embeds the question, pulls a **candidate pool** from the store (wider than `top_k` when reranking is on), applies the reranker (or the legacy keyword boost), optionally expands via GraphRAG, and returns ranked `SearchResult`s with scores. |
| **MultiRetriever** | `retriever.py` | Same contract, but pools candidates from **several collections at once** and reranks them on a single global scale — this is what powers cross-domain queries and `ci-eval --domain all`. A broken collection is skipped, never fatal. |
| **Reranker** | `reranker.py` | A **cross-encoder** that re-scores each (question, chunk) pair jointly — far more precise than the bi-encoder vector search. Lazy-loaded, sigmoid-normalised to `[0,1]`, opt-in via `RERANK_ENABLED`. Biggest single lever for context precision. |
| **LLM provider** | `llm/` | Provider-agnostic generation behind one protocol. Switch Ollama ↔ OpenAI ↔ vLLM ↔ Claude with one env var; per-module overrides (`CI_LLM_*`, …) let each domain use a different model. |
| **Escalation** | `escalation.py` | Safety net: when retrieval confidence drops below `ESCALATION_THRESHOLD` and a Claude key is present, the answer is escalated to the cloud — otherwise everything stays local. |
| **Intent Routing** | `intent.py` | Classifies each query as RAG / SKILL / AGENT (fast heuristic first, LLM only for ambiguous cases). Invisible to the user; always falls back to plain RAG on any failure. |
| **GraphRAG** | `graph/` | Builds a NetworkX dependency graph from `calls`/`imports` metadata, then expands retrieved context with structurally-related code (callers + callees). Optional — missing graph degrades gracefully. |
| **Evaluation** | `evaluation/` | The RAGAS pipeline behind `ci-eval`: generates a testset, runs retrieval+generation, and scores faithfulness / relevancy / context precision / recall against KPI targets. |

### The domain modules

Each module is a **thin shell** around the engine: a parser/ingester that produces chunks, plus a
FastAPI server (and chat UI) on its own port. They share the retriever, embedder, store, and LLM
layer entirely.

- **CodeIntelligence** — parses a repository (Python AST, Tree-sitter/regex for TS/Go/Java/Rust,
  plus YAML/SQL/MD) into code chunks; serves the code RAG on `ci-serve`.
- **DocIntelligence** — ingests company documents (3-level PDF, DOCX, XLSX, TXT/MD) into doc
  chunks; serves the doc RAG on `di-serve`.
- **MentorIntelligence** — adaptive onboarding: detects a newcomer's profile, manages sessions,
  builds a learning path, and answers across `code`+`doc`+`mentor` in one query.
- **SkillIntelligence** — turns procedures into step-by-step guided sessions; each step retrieves
  cross-domain context before generating grounded LLM guidance.
- **AgentIntelligence** — a ReAct loop for questions a single retrieval can't answer; reasons,
  calls tools (`search_code/docs/practices`, `analyze_impact`), observes, and iterates.
- **ProposalIntelligence** — answers questionnaires/RFPs in your house style: ingests a corpus of
  past Q&A, embeds the *question* for matching, and uses the retrieved pairs as few-shot style
  exemplars (`anchored`/`commercial` modes); serves a web UI + API on `pi-serve`.

The **launcher** (`intelligence_ui`, `is-launch`) is the operator's cockpit — it starts, stops,
and monitors every server from one dashboard. The **eval runner** (`intelligence_eval`, `is-eval`)
drives quality measurement across modules.

### Request lifecycle (a single `/api/v1/query`)

1. **Route** — Intent Routing classifies the question (RAG / SKILL / AGENT). Simple factual
   questions go straight to RAG.
2. **Retrieve** — the Retriever embeds the question and pulls a candidate pool from ChromaDB
   (a single collection, or all of them via MultiRetriever).
3. **Rerank** — the cross-encoder re-orders the candidates by joint (question, chunk) relevance
   and cuts to `top_k` (or the legacy keyword boost when reranking is off).
4. **Expand (optional)** — if a dependency graph exists, GraphRAG adds structurally-related code.
5. **Generate** — the chosen LLM backend writes an answer grounded in the retrieved chunks.
6. **Escalate (conditional)** — if confidence is below threshold and a Claude key is set, the
   answer is regenerated by the cloud model.
7. **Respond** — the client receives the answer plus **source citations**, a confidence score,
   and the backend used — streamed word-by-word over SSE in the chat UI.

### Source tree

```
IntelligenceSuite/
├── intelligence_core/       # Shared engine — all of the above lives here
│   ├── parsers/             #   class-based Tree-sitter parsers (TS, Go, Java, Rust)
│   ├── llm/                 #   provider-agnostic LLM backends (Ollama/OpenAI/vLLM/Claude)
│   ├── graph/               #   NetworkX dependency graph + GraphRAG + ci-graph CLI
│   └── evaluation/          #   RAGAS pipeline (ci-eval)
├── CodeIntelligence/        # Code RAG: Python AST + Tree-sitter/regex, YAML, SQL, MD parsers
├── DocIntelligence/         # Doc RAG: PDF (3-level), DOCX, XLSX, TXT
├── MentorIntelligence/      # Adaptive onboarding: profile, session, path, orchestrator
├── SkillIntelligence/       # Procedural guidance: skill registry, executor, cross-domain RAG
│   └── skills/              #   bundled Python skill definitions
├── AgentIntelligence/       # ReAct agent: tool calling, multi-hop reasoning, ai-serve
├── ProposalIntelligence/    # Questionnaire/RFP auto-answer in house style (qa_parser, prompts, web UI)
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
