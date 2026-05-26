# Guida — Come usare CodeIntelligence

## Cosa fa CodeIntelligence

CodeIntelligence indicizza il codice sorgente di un repository e permette di
fare domande in linguaggio naturale sul codice. Supporta Python (AST preciso),
TypeScript, JavaScript, Go, SQL, YAML e Markdown.

## Pipeline completo

### Step 1 — Parse del repository
```bash
ci-parse /path/to/repo
```
Produce `chunks.jsonl` con tutti i chunk del codice. Ogni chunk contiene:
- ID deterministico: `code::function::path/file.py::nome_funzione`
- Testo human-readable con firma, docstring e corpo della funzione
- Metadati: start_line, end_line, decoratori, chiamate

Cartelle automaticamente escluse dal parsing:
`build/`, `dist/`, `venv/`, `.venv/`, `node_modules/`, `__pycache__`

### Step 2 — Embedding
```bash
ci-embed                        # usa chunks.jsonl nella directory corrente
ci-embed --file altro_file.jsonl  # file alternativo
```

Il comando embeds tutti i chunk e li salva in ChromaDB.
Path ChromaDB: `~/.intelligence_suite/chroma` (assoluto, indipendente dalla directory)
Collezione usata: `code_intelligence`

**Prima esecuzione:** lenta (embedding di tutti i chunk)
**Successive:** solo i chunk nuovi o modificati (se usi --incremental)

### Step 3 — Avvia il server
```bash
ci-serve                        # porta 8080 (default)
```

Endpoints disponibili:
- `GET /` — chat UI streaming nel browser
- `GET /health` — stato server, chunk count, LLM backend
- `POST /api/v1/query` — query non-streaming (JSON)
- `POST /api/v1/stream` — query streaming (SSE)

## Esempi di domande efficaci

Domande che funzionano bene su CodeIntelligence:
- "Dove è gestita l'autenticazione?"
- "Come funziona il meccanismo di retry in httpx?"
- "Quali funzioni chiamano ChromaDB direttamente?"
- "Come è implementato il parser Python?"
- "Mostrami la firma del metodo embed_one"

Domande meno adatte (meglio DocIntelligence):
- "Cos'è CodeIntelligence?" → risponde ma meglio su Doc
- "Come installo la libreria?" → meglio su Doc

## Usare l'API Python direttamente

```python
from pathlib import Path
from CodeIntelligence.parse_repo import parse_repo
from CodeIntelligence.embed_chunks import embed_chunks
from intelligence_core.retriever import Retriever

# Parse e embed (una tantum)
chunks = parse_repo(Path("/path/to/repo"), output=Path("chunks.jsonl"))
embed_chunks(Path("chunks.jsonl"))

# Query
retriever = Retriever.load_default(collection_name="code_intelligence")
results = retriever.search("Come funziona il retriever?", domain="code", top_k=5)
for r in results:
    print(f"[{r.score:.3f}] {r.chunk['source']} — {r.chunk['text'][:100]}")
```

## Configurazione LLM per CodeIntelligence

Per usare un modello specializzato per il codice (consigliato):
```env
CI_LLM_BACKEND=ollama
CI_LLM_MODEL=qwen2.5-coder:7b   # ottimizzato per codice
```

Per usare un endpoint vLLM aziendale:
```env
CI_LLM_BACKEND=openai
CI_LLM_MODEL=codellama:34b
CI_LLM_BASE_URL=http://gpu-server:8000/v1
```

## Troubleshooting

**0 chunks nel server:**
ChromaDB non trova dati. Ricontrolla che `ci-embed` sia stato eseguito.
```bash
curl http://localhost:8080/health
# {"chunks_indexed": 0, ...} → devi fare ci-embed
```

**DuplicateIDError:**
Hai cartelle `build/` o `dist/` nel repo.
```bash
rm -rf build/ dist/
ci-parse /path/to/repo
ci-embed
```

**Ollama non raggiungibile:**
```bash
ollama serve
ollama pull qwen2.5-coder:7b
```
Oppure: `EMBED_BACKEND=st` nel `.env` per embedding offline.
