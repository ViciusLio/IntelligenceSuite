# IntelligenceSuite

**Retrieve enterprise knowledge in seconds, not hours.**

A modular RAG suite for enterprise on-premise environments.  
Zero mandatory cloud. Zero lock-in. Everything under your control.

---

## The Problem

How much time does your team waste every week hunting down where a function is implemented,
re-reading a procedure to recall one detail, or asking colleagues what that undocumented
service actually does?

IntelligenceSuite indexes your codebase and your company documents, then answers in natural
language with precise source citations - entirely on-premise.

---

## Modules

| Library              | Domain                 | Status       |
|----------------------|------------------------|--------------|
| `CodeIntelligence`   | Source code            | ✅ Stable    |
| `DocIntelligence`    | Company documents      | ✅ Stable    |
| `MentorIntelligence` | Adaptive onboarding    | ✅ Stable    |
| `intelligence_core`  | Shared layer           | ✅ Stable    |

---

## Quickstart — CodeIntelligence

```bash
pip install -e ".[dev]"
cp .env.example .env

# Index a repository
python -m CodeIntelligence.parse_repo /path/to/repo
python -m CodeIntelligence.embed_chunks

# Start the RAG server
python -m CodeIntelligence.rag_server

# Query it
curl -X POST http://localhost:8080/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Where is authentication handled?"}'
```

## Quickstart — DocIntelligence

```bash
pip install -e ".[pdf,docx,xlsx]"

# Ingest documents (PDF, DOCX, XLSX, TXT, MD)
python -m DocIntelligence.ingest_docs /path/to/docs
python -m DocIntelligence.embed_docs

# Start the doc server
python -m DocIntelligence.doc_server

# Query it
curl -X POST http://localhost:8080/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the production deploy prerequisites?"}'
```

## Quickstart — MentorIntelligence

```bash
pip install -e ".[pdf,docx,xlsx]"

# (Optional) ingest company best practices
mkdir practices
echo "# Naming conventions\n..." > practices/git_convention.md
python -m MentorIntelligence.content.ingest_practices ./practices

# Start the mentor server
python -m MentorIntelligence.mentor_server

# Start an onboarding session
curl -X POST http://localhost:8080/api/v1/mentor/onboard \
  -H "Content-Type: application/json" \
  -d '{"user_name": "Alice", "intro": "I am a Python developer, first day here."}'

# Ask questions within your onboarding path
curl -X POST http://localhost:8080/api/v1/mentor/ask \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "question": "How does authentication work?"}'
```

---

## Architecture

```
IntelligenceSuite/
├── intelligence_core/       # Shared layer: chunks, embedder, store, retriever, escalation
├── CodeIntelligence/        # Source code RAG: Python AST, TS, Go, YAML, SQL, MD
├── DocIntelligence/         # Document RAG: PDF (3-level), DOCX, XLSX, TXT
└── MentorIntelligence/      # Adaptive onboarding: profile, session, path, orchestrator
```

### Embedding backends (via `intelligence_core`)

| Backend              | Use case                          | Config              |
|----------------------|-----------------------------------|---------------------|
| Ollama (local)       | Default — fully on-premise        | `EMBEDDER=ollama`   |
| SentenceTransformer  | CPU-only, no GPU needed           | `EMBEDDER=st`       |
| Claude / Voyage      | Cloud escalation for hard queries | `EMBEDDER=claude`   |

### Vector store

| Store    | Status         | Notes                    |
|----------|----------------|--------------------------|
| ChromaDB | ✅ Default      | Local, zero-config       |
| pgvector | 🔶 Roadmap     | Enterprise, multi-tenant |

---

## KPI Targets

| Metric     | Code   | Docs   |
|------------|--------|--------|
| Hit@1      | > 60%  | > 55%  |
| Hit@5      | > 85%  | > 80%  |
| MRR        | > 0.70 | > 0.65 |
| Latency P50| < 300ms| < 400ms|

---

## Hardware Requirements

| Scenario                     | Hardware                         |
|------------------------------|----------------------------------|
| Dev / local testing          | Mac or PC with 16 GB RAM         |
| Team of 1-10 people          | Server with 32 GB RAM            |
| Team of 10-50 people (GPU)   | RTX 3090/4090 + 64 GB RAM        |
| Team 50+ people              | pgvector + dedicated GPU         |

---

## Configuration

Copy `.env.example` to `.env` and edit:

```env
EMBEDDER=ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=nomic-embed-text
STORE_BACKEND=chroma
CHROMA_DIR=.chroma
ESCALATION_THRESHOLD=0.65
```

---

## Test Suite

```bash
pip install -e ".[dev]"
pytest tests/ -v
# 54 passed, 5 skipped (KPI tests require indexed store), 0 failed
```

---

## License

MIT — see [LICENSE](LICENSE)

---

> See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions and [docs/](docs/) for presentations.
