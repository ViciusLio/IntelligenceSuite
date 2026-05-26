# Onboarding — Nuovo Developer su IntelligenceSuite

## Benvenuto nel progetto

IntelligenceSuite è una suite RAG modulare on-premise per recuperare conoscenza
aziendale in linguaggio naturale. Indicizza codice sorgente e documenti aziendali,
poi risponde a domande con citazioni precise delle fonti — tutto locale, zero cloud.

## Primo giorno — Setup ambiente

### Prerequisiti
- Python 3.10 o superiore
- Ollama installato (https://ollama.com) — per LLM e embedding locali
- Git configurato con profilo personale

### Installazione base
```bash
pip install intelligence-suite
ollama serve
ollama pull nomic-embed-text    # modello embedding
ollama pull qwen2.5-coder:7b    # modello generazione
```

### Installazione con tutti gli extra
```bash
pip install "intelligence-suite[all]"
```

### Clona il repository
```bash
git clone https://github.com/ViciusLio/IntelligenceSuite.git
cd IntelligenceSuite
pip install -e ".[dev]"
```

## Secondo giorno — Prima indicizzazione

Indicizza il codice del progetto stesso (ottimo per capire la libreria):
```bash
ci-parse .                     # analizza il codice → chunks.jsonl
ci-embed                       # embedding → ChromaDB
ci-serve                       # avvia server → http://localhost:8080
```

Poi apri http://localhost:8080 e chiedi:
- "Come funziona il retriever?"
- "Quali LLM backend sono supportati?"
- "Come è implementato il meccanismo di escalation?"

## Terzo giorno — Comprendi l'architettura

I tre moduli principali:
- **CodeIntelligence** (porta 8080): domande sul codice sorgente
- **DocIntelligence** (porta 8081): domande su documenti aziendali (PDF, DOCX, XLSX)
- **MentorIntelligence** (porta 8082): onboarding adattivo con sessioni personalizzate

Ogni modulo ha il suo pipeline indipendente:
```
parse/ingest → embed → ChromaDB → serve → query
```

## Quarta giornata — Configura il tuo ambiente

Copia `.env.example` in `.env` e personalizza:
```bash
cp .env.example .env
```

Impostazioni consigliate per sviluppo:
```env
LLM_BACKEND=ollama
EMBED_BACKEND=st
ST_MODEL=paraphrase-multilingual-MiniLM-L12-v2
LOG_LEVEL=DEBUG
```

## Convenzioni del progetto

- Ogni file max 400 righe — se cresce, sta facendo troppe cose
- I chunk sono testo leggibile da un umano — non blob opachi
- Zero lock-in: embedder, LLM e vector store sono tutti swappabili via `.env`
- Un file rotto non crasha mai il pipeline (best-effort ingestion)

## Test suite

```bash
pytest tests/ -v
# 54 passed, 5 skipped (KPI — richiedono store indicizzato), 0 failed
```

## Contatti e risorse

- Repository: https://github.com/ViciusLio/IntelligenceSuite
- PyPI: https://pypi.org/project/intelligence-suite/
- Issues: https://github.com/ViciusLio/IntelligenceSuite/issues
