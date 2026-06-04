# Continuous Integration — running the test suite

IntelligenceSuite ships a deterministic test suite that runs **offline**: no
Ollama, no network, no optional extra, no disk state. Retrieval-quality (KPI)
tests run against a disk-less, in-memory ChromaDB loaded with versioned
synthetic fixtures (`tests/fixtures/`), so the quality of retrieval is verified
on every commit instead of being skipped when no live index exists.

## Quick reference

| Command | What it runs |
|---|---|
| `pytest tests/ -v` | The whole suite. |
| `pytest -m kpi` | Only the deterministic retrieval-quality (KPI) tests. |
| `pytest -m "not slow"` | Everything except tests needing a real embedding backend. |
| `pytest -m "kpi and not slow"` | KPI tests only, guaranteed offline. |

## Markers

Declared in `pyproject.toml` under `[tool.pytest.ini_options]`:

- **`kpi`** — deterministic retrieval-quality tests on an in-memory store.
  These **always run in CI** (they never skip) and fail for real if the
  retriever is broken: wrong collection, embeddings not loaded, ranking
  inverted, etc.
- **`slow`** — tests that need a real embedding backend (Ollama / sentence-
  transformers) or the network. Exclude them in standard CI with
  `pytest -m "not slow"`.

## How the KPI tests work

- Synthetic fixtures live in `tests/fixtures/`:
  `kpi_code_chunks.json`, `kpi_doc_chunks.json`, `kpi_qa.json`. The data is
  realistic but entirely synthetic — no confidential content.
- `tests/conftest.py` provides a dependency-free `HashingEmbedder` (bag-of-words
  → cosine similarity reflects lexical overlap) and fixtures that mount an
  in-memory `ChromaStore(persist_dir=":memory:")`, load the chunks, and return a
  ready `Retriever`. The collection name comes from `paths.collection_name(...)`
  (the Fase-1 naming), so with the default project it is the classic
  `code_intelligence` / `doc_intelligence`.
- Thresholds (`tests/test_kpi.py::KPI_MIN`) are more generous than production
  because synthetic data is easier to retrieve — but a broken retriever still
  fails them.

## What stays out of CI

`ci-eval` (the RAGAS evaluation pipeline) requires a live LLM **and** a populated
store, so it is **not** part of standard CI. Run it manually against a real index:

```bash
pip install 'intelligence-suite[eval]'
ci-eval --domain all
```

The legacy `TestKPIThresholds` in `tests/test_intelligence_suite.py` still skips
when no live index is present — it measures the *production* system, not the
synthetic fixtures. The `kpi`-marked tests are the ones that run deterministically.
