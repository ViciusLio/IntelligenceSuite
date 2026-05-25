"""Entry point: scansiona una directory di documenti e produce chunk JSONL."""

from __future__ import annotations
import argparse
from pathlib import Path

from DocIntelligence.parsers import get_parser
from intelligence_core.chunk import chunk_to_jsonl


def ingest_docs(docs_path: Path, output: Path = None) -> list[dict]:
    chunks = []
    skipped = 0
    for file in sorted(docs_path.rglob("*")):
        if not file.is_file():
            continue
        if any(part.startswith(".") for part in file.parts):
            continue
        parser = get_parser(file)
        if parser is None:
            skipped += 1
            continue
        file_chunks = parser.parse_file(file, docs_path)
        chunks.extend(file_chunks)
        print(f"  {file.name}: {len(file_chunks)} chunk")

    print(f"Totale: {len(chunks)} chunk, {skipped} file senza parser")

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(chunk_to_jsonl(c) + "\n")
        print(f"Output: {output}")

    return chunks


def main():
    parser = argparse.ArgumentParser(description="Ingesta documenti in chunk JSONL")
    parser.add_argument("docs", nargs="?", default="./docs")
    parser.add_argument("-o", "--output", default="doc_chunks.jsonl")
    args = parser.parse_args()
    ingest_docs(Path(args.docs), Path(args.output))


if __name__ == "__main__":
    main()
