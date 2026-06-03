"""Genera un testset di domande/risposte dal corpus indicizzato.

Operazione costosa (chiamate LLM) — eseguita una volta e cachata su disco.
Adattato a RAGAS 0.2.x: TestsetGenerator(llm, embedding_model) +
generate_with_langchain_docs(documents, testset_size=...).
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Literal

from intelligence_core.evaluation.paths import get_all_chunk_paths, get_chunks_path

Domain = Literal["code", "doc", "mentor", "all"]

# Number of source documents fed into the RAGAS knowledge-graph builder.
# RAGAS builds a KG over every document and then runs find_indirect_clusters,
# a recursive DFS whose cost explodes on large/dense graphs (it effectively
# hangs at ~1000+ nodes). Capping the corpus keeps generation tractable —
# a few hundred docs is far more than enough for a 50-question testset.
DEFAULT_MAX_DOCS = 150
# Chunks shorter than this can't get a meaningful summary from RAGAS
# ("Node ... does not have a summary"), which over-connects the graph.
DEFAULT_MIN_CHARS = 100


def generate_testset(
    domain: Domain,
    test_size: int = 50,
    force_regenerate: bool = False,
    max_docs: int = DEFAULT_MAX_DOCS,
    min_chunk_chars: int = DEFAULT_MIN_CHARS,
) -> list[dict]:
    cache_path = Path(f"tests/eval/{domain}_testset.jsonl")

    if cache_path.exists() and not force_regenerate:
        rows = _load_from_cache(cache_path)
        # --samples deve poter ridurre senza rigenerare (zero chiamate LLM).
        # Per averne di più della cache serve --regenerate.
        if test_size and len(rows) > test_size:
            print(
                f"Carico testset dalla cache: {cache_path} "
                f"({len(rows)} domande → uso le prime {test_size})"
            )
            return rows[:test_size]
        if test_size and len(rows) < test_size:
            print(
                f"Carico testset dalla cache: {cache_path} ({len(rows)} domande). "
                f"Richieste {test_size}: usa --regenerate per generarne di più."
            )
        else:
            print(f"Carico testset dalla cache: {cache_path} ({len(rows)} domande)")
        return rows

    if domain == "all":
        paths = get_all_chunk_paths()
        if not paths:
            raise FileNotFoundError(
                "Nessun file di chunk trovato per l'eval integrato 'all' "
                "(chunks.jsonl / doc_chunks.jsonl / mentor_chunks.jsonl). "
                "Esegui prima ci-parse/ci-embed (+ di-* e mi-* per gli altri domini)."
            )
        documents = []
        for p in paths:
            documents.extend(_load_chunks_as_documents(p, min_chars=min_chunk_chars))
        print(
            f"Caricati {len(documents)} documenti da {len(paths)} file "
            f"{[p.name for p in paths]} (filtro lunghezza >= {min_chunk_chars} caratteri)"
        )
    else:
        chunks_path = _get_chunks_path(domain)
        if not chunks_path.exists():
            raise FileNotFoundError(
                f"Chunks non trovati per '{domain}' ({chunks_path}). "
                f"Esegui prima: ci-parse e ci-embed."
            )

        documents = _load_chunks_as_documents(chunks_path, min_chars=min_chunk_chars)
        print(
            f"Caricati {len(documents)} documenti per '{domain}' "
            f"(dopo filtro lunghezza >= {min_chunk_chars} caratteri)"
        )

    documents = _cap_documents(documents, max_docs)
    print(
        f"Uso {len(documents)} documenti per costruire il knowledge graph RAGAS "
        f"(cap: {max_docs})"
    )

    from ragas.testset import TestsetGenerator

    from intelligence_core.evaluation.ragas_factory import (
        get_ragas_embeddings,
        get_ragas_llm,
    )

    generator = TestsetGenerator(
        llm=get_ragas_llm(),
        embedding_model=get_ragas_embeddings(),
    )
    testset = generator.generate_with_langchain_docs(
        documents,
        testset_size=test_size,
    )

    rows = testset.to_pandas().to_dict(orient="records")
    rows = [_normalize_row(r) for r in rows]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    _save_to_cache(rows, cache_path)
    print(f"Testset salvato: {cache_path} ({len(rows)} domande)")
    return rows


def _normalize_row(row: dict) -> dict:
    """RAGAS 0.2 usa 'user_input'/'reference'; normalizziamo a question/ground_truth."""
    return {
        "question": row.get("user_input") or row.get("question", ""),
        "ground_truth": row.get("reference") or row.get("ground_truth", ""),
        **{k: v for k, v in row.items() if k not in ("user_input", "reference")},
    }


def _load_chunks_as_documents(chunks_path: Path, min_chars: int = 0) -> list:
    from langchain_core.documents import Document

    documents = []
    with open(chunks_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            chunk = json.loads(line)
            text = chunk.get("text", "")
            if len(text.strip()) < min_chars:
                continue
            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": chunk.get("source", ""),
                        "type": chunk.get("type", ""),
                        "domain": chunk.get("domain", ""),
                    },
                )
            )
    return documents


def _cap_documents(documents: list, max_docs: int) -> list:
    """Deterministically sample down to max_docs so the RAGAS knowledge graph
    stays small enough that find_indirect_clusters terminates quickly."""
    if max_docs and len(documents) > max_docs:
        return random.Random(42).sample(documents, max_docs)
    return documents


def _get_chunks_path(domain: Domain) -> Path:
    return get_chunks_path(domain)


def _load_from_cache(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _save_to_cache(rows: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
