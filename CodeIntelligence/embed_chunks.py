"""Legge chunk JSONL, aggiunge embedding, salva il JSONL aggiornato."""

from __future__ import annotations
import argparse
import json
from pathlib import Path

from intelligence_core.chunk import chunk_from_jsonl, chunk_to_jsonl
from intelligence_core.embedder import get_embedder
from intelligence_core.config import settings


def embed_chunks(input_file: Path, output_file: Path = None, incremental: bool = False):
    output_file = output_file or input_file
    embedder = get_embedder()

    chunks = []
    with input_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(chunk_from_jsonl(line))

    to_embed = [c for c in chunks if not incremental or not c.get("embedding")]
    print(f"Embedding {len(to_embed)}/{len(chunks)} chunk...")

    batch_size = settings.embed_batch_size
    for i in range(0, len(to_embed), batch_size):
        batch = to_embed[i: i + batch_size]
        texts = [c["text"] for c in batch]
        embeddings = embedder.embed(texts)
        for chunk, emb in zip(batch, embeddings):
            chunk["embedding"] = emb
        print(f"  Batch {i // batch_size + 1}: {len(batch)} chunk embedded")

    with output_file.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(chunk_to_jsonl(c) + "\n")

    print(f"Salvato: {output_file}")


def incremental_update(input_file: Path, output_file: Path = None):
    """Aggiunge embedding solo ai chunk nuovi (checksum diverso)."""
    embed_chunks(input_file, output_file, incremental=True)


def main():
    parser = argparse.ArgumentParser(description="Aggiunge embedding ai chunk JSONL")
    parser.add_argument("input", help="File JSONL con chunk")
    parser.add_argument("-o", "--output", help="File output (default: sovrascrive input)")
    parser.add_argument("--incremental", action="store_true")
    args = parser.parse_args()
    embed_chunks(
        Path(args.input),
        Path(args.output) if args.output else None,
        incremental=args.incremental,
    )


if __name__ == "__main__":
    main()
