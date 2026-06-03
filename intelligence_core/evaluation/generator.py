"""Genera un testset di domande/risposte dal corpus indicizzato.

Operazione costosa (chiamate LLM) — eseguita una volta e cachata su disco.
Adattato a RAGAS 0.2.x: TestsetGenerator(llm, embedding_model) +
generate_with_langchain_docs(documents, testset_size=...).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from intelligence_core.evaluation.paths import get_chunks_path

Domain = Literal["code", "doc", "mentor"]


def generate_testset(
    domain: Domain,
    test_size: int = 50,
    force_regenerate: bool = False,
) -> list[dict]:
    cache_path = Path(f"tests/eval/{domain}_testset.jsonl")

    if cache_path.exists() and not force_regenerate:
        print(f"Carico testset dalla cache: {cache_path}")
        return _load_from_cache(cache_path)

    chunks_path = _get_chunks_path(domain)
    if not chunks_path.exists():
        raise FileNotFoundError(
            f"Chunks non trovati per '{domain}' ({chunks_path}). "
            f"Esegui prima: ci-parse e ci-embed."
        )

    documents = _load_chunks_as_documents(chunks_path)
    print(f"Caricati {len(documents)} documenti per '{domain}'")

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


def _load_chunks_as_documents(chunks_path: Path) -> list:
    from langchain_core.documents import Document

    documents = []
    with open(chunks_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            chunk = json.loads(line)
            documents.append(
                Document(
                    page_content=chunk["text"],
                    metadata={
                        "source": chunk.get("source", ""),
                        "type": chunk.get("type", ""),
                        "domain": chunk.get("domain", ""),
                    },
                )
            )
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
