"""Aggiunge embedding ai chunk JSONL di DocIntelligence."""

from __future__ import annotations
import argparse
from pathlib import Path

from intelligence_core.chunk import chunk_from_jsonl, chunk_to_jsonl
from intelligence_core.embedder import get_embedder
from intelligence_core.config import settings


def embed_docs(input_file: Path, output_file: Path = None):
    output_file = output_file or input_file
    embedder = get_embedder()
    chunks = []
    with input_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(chunk_from_jsonl(line))

    print(f"Embedding {len(chunks)} chunk...")
    batch_size = settings.embed_batch_size
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i: i + batch_size]
        embeddings = embedder.embed([c["text"] for c in batch])
        for chunk, emb in zip(batch, embeddings):
            chunk["embedding"] = emb

    with output_file.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(chunk_to_jsonl(c) + "\n")
    print(f"Salvato: {output_file}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default="doc_chunks.jsonl", help="File JSONL con chunk (default: doc_chunks.jsonl)")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()
    embed_docs(Path(args.input), Path(args.output) if args.output else None)


if __name__ == "__main__":
    main()
