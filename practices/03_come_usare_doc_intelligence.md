# Guida — Come usare DocIntelligence

## Cosa fa DocIntelligence

DocIntelligence indicizza documenti aziendali in vari formati e permette di
fare domande sui contenuti in linguaggio naturale. Supporta PDF (con fallback
OCR per documenti scansionati), DOCX, XLSX, TXT e Markdown.

## Formati supportati

| Formato | Parser | Note |
|---------|--------|------|
| PDF | pdfplumber → OCR → raw binary | 3 livelli di fallback, mai perde una pagina |
| DOCX | python-docx | Sezioni heading + body |
| XLSX | openpyxl | Chunk per foglio |
| TXT / MD | Built-in | Split per heading o righe |

## Pipeline completo

### Step 1 — Ingestione documenti
```bash
di-ingest /path/to/docs
```
Produce `doc_chunks.jsonl`. Accetta una cartella con file misti.

### Step 2 — Embedding
```bash
di-embed                        # usa doc_chunks.jsonl nella directory corrente
```
Salva in ChromaDB, collezione `doc_intelligence`.

### Step 3 — Avvia il server
```bash
di-serve                        # porta 8081
```

Apri http://localhost:8081 per la chat UI.

## Esempi di domande efficaci

- "Quali sono i prerequisiti per il deploy in produzione?"
- "Riassumimi la procedura di rilascio"
- "Cosa dice l'ADR sul vector store?"
- "Quali KPI sono definiti per CodeIntelligence?"
- "Quali modelli di embedding sono supportati?"
- "Come si configura l'escalation policy?"

## Usare l'API Python

```python
from pathlib import Path
from DocIntelligence.ingest_docs import ingest_docs
from DocIntelligence.embed_docs import embed_docs
from intelligence_core.retriever import Retriever
from intelligence_core.llm import get_llm_provider

# Ingestione e embedding (una tantum)
chunks = ingest_docs(Path("/path/to/docs"), output=Path("doc_chunks.jsonl"))
embed_docs(Path("doc_chunks.jsonl"))

# Query
retriever = Retriever.load_default(collection_name="doc_intelligence")
llm = get_llm_provider()

results = retriever.search("Prerequisiti deploy produzione", domain="doc", top_k=5)
context = "\n\n---\n\n".join(r.chunk["text"] for r in results[:3])
answer = llm.generate("Prerequisiti deploy produzione", context)
print(answer)
```

## Configurazione LLM per DocIntelligence

Per documenti in italiano, Mistral è più fluente:
```env
DI_LLM_BACKEND=ollama
DI_LLM_MODEL=mistral:7b
```

Per documenti complessi che richiedono alta qualità:
```env
DI_LLM_BACKEND=claude
DI_LLM_MODEL=claude-sonnet-4-5
```

## Requisiti per formati avanzati

```bash
# PDF strutturati
pip install "intelligence-suite[pdf]"

# PDF scansionati (OCR) — richiede anche Tesseract sul sistema
pip install "intelligence-suite[pdf,ocr]"
# Windows: scarica Tesseract da https://github.com/UB-Mannheim/tesseract/wiki

# Word documents
pip install "intelligence-suite[docx]"

# Excel
pip install "intelligence-suite[xlsx]"
```

## Nota sulla confidence

DocIntelligence risponde a domande concettuali — la confidence tende a essere
più bassa (0.4–0.6) rispetto a CodeIntelligence (0.7–0.9) perché il testo
dei documenti è più vario. Se la confidence scende sotto 0.70 e hai
`ANTHROPIC_API_KEY` configurata, la risposta viene automaticamente escalata
a Claude per maggiore qualità.
