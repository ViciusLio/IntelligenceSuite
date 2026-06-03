"""pi-ingest — corpus di coppie Q&A → chunk JSONL (1 chunk = 1 coppia).

Ogni chunk ha:
    text     = "D: <domanda>\\n\\nR: <risposta>"   (coppia intera, per il contesto)
    metadata = {"question": ..., "answer": ..., "name": ...}

L'embedding (passo successivo, ``pi-embed``) viene calcolato sulla **domanda**,
così il match è domanda-su-domanda.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from intelligence_core.chunk import chunk_to_jsonl, make_chunk
from ProposalIntelligence.qa_parser import parse_qa_pairs

_STRUCTURED_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".xlsx"}


def _locator(question: str) -> str:
    return hashlib.sha1(question.strip().lower().encode("utf-8")).hexdigest()[:16]


def _pair_to_chunk(question: str, answer: str, source: str) -> dict:
    chunk = make_chunk(
        domain="qa",
        type_="qa_pair",
        locator=_locator(question),
        text=f"D: {question}\n\nR: {answer}",
        source=source,
        language="mixed",
        metadata={
            "question": question,
            "answer":   answer,
            "name":     question[:80],
        },
    )
    return chunk


def ingest_qa(corpus_path: Path, output: Path | None = None) -> list[dict]:
    """Legge il corpus (file singolo o directory) e produce chunk JSONL."""
    files: list[Path]
    if corpus_path.is_dir():
        files = sorted(
            f for f in corpus_path.rglob("*")
            if f.is_file()
            and f.suffix.lower() in _STRUCTURED_SUFFIXES
            and not any(p.startswith(".") for p in f.parts)
        )
    else:
        files = [corpus_path]

    chunks: list[dict] = []
    seen_ids: set[str] = set()
    for f in files:
        rel = (
            str(f.relative_to(corpus_path)).replace("\\", "/")
            if corpus_path.is_dir() else f.name
        )
        try:
            pairs = parse_qa_pairs(f)
        except Exception as e:
            print(f"  WARN: {f.name} non parsato ({e})")
            continue
        kept = 0
        for q, a in pairs:
            chunk = _pair_to_chunk(q, a, rel)
            if chunk["id"] in seen_ids:
                continue   # domanda duplicata → tieni la prima
            seen_ids.add(chunk["id"])
            chunks.append(chunk)
            kept += 1
        print(f"  {f.name}: {kept} coppie Q&A")

    print(f"Totale: {len(chunks)} coppie Q&A da {len(files)} file")

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as fh:
            for c in chunks:
                fh.write(chunk_to_jsonl(c) + "\n")
        print(f"Output: {output}")

    return chunks


def main():
    parser = argparse.ArgumentParser(
        description="Ingesta un corpus di coppie Domanda/Risposta in chunk JSONL"
    )
    parser.add_argument(
        "corpus", nargs="?", default="./qa_corpus",
        help="File o directory col corpus Q&A (MD/CSV/XLSX, tabella o marcatori D:/R:)",
    )
    parser.add_argument("-o", "--output", default="qa_chunks.jsonl")
    args = parser.parse_args()
    ingest_qa(Path(args.corpus), Path(args.output))


if __name__ == "__main__":
    main()
