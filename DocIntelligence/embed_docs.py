"""Embed doc chunks from JSONL and load into ChromaDB."""

from __future__ import annotations
import argparse
from pathlib import Path

from intelligence_core.chunk import chunk_from_jsonl, chunk_to_jsonl
from intelligence_core.embedder import get_embedder
from intelligence_core.config import settings

COLLECTION_NAME = "doc_intelligence"


def _warn_zero_embeddings(chunks: list[dict]) -> None:
    zero = sum(
        1 for c in chunks
        if c.get("embedding") and all(v == 0.0 for v in c["embedding"])
    )
    if zero:
        print(f"\n  ⚠  WARNING: {zero}/{len(chunks)} chunks have zero embeddings.")
        print("     Ollama was unreachable during embedding. To fix:")
        print("       1.  ollama serve")
        print("       2.  ollama pull nomic-embed-text")
        print("       3.  Re-run:  di-embed")
        print("     Or switch to a local CPU model: EMBED_BACKEND=st in .env\n")


def embed_docs(
    input_file: Path,
    output_file: Path = None,
    collection_name: str = COLLECTION_NAME,
) -> list[dict]:
    """
    Full pipeline step:
      1. Read doc chunks from JSONL
      2. Compute embeddings
      3. Write updated JSONL
      4. Upsert into ChromaDB — collection ready for di-serve

    Args:
        input_file:       JSONL file produced by di-ingest.
        output_file:      Destination JSONL (default: overwrite input).
        collection_name:  ChromaDB collection (default: ``doc_intelligence``).
    """
    output_file = output_file or input_file
    embedder    = get_embedder()

    chunks: list[dict] = []
    with input_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(chunk_from_jsonl(line))

    print(f"Embedding {len(chunks)} chunks...")
    batch_size = settings.embed_batch_size
    for i in range(0, len(chunks), batch_size):
        batch      = chunks[i: i + batch_size]
        embeddings = embedder.embed([c["text"] for c in batch])
        for chunk, emb in zip(batch, embeddings):
            chunk["embedding"] = emb
        print(f"  batch {i // batch_size + 1}: {len(batch)} chunks embedded")

    _warn_zero_embeddings(chunks)

    # ── Write JSONL ──────────────────────────────────────────────────────────
    with output_file.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(chunk_to_jsonl(c) + "\n")
    print(f"JSONL saved: {output_file}")

    # ── Load into ChromaDB ───────────────────────────────────────────────────
    from intelligence_core.store import ChromaStore
    store = ChromaStore(collection_name=collection_name)
    store.add(chunks)
    print(f"ChromaDB '{collection_name}': {store.count()} total chunks indexed")

    return chunks


def main():
    parser = argparse.ArgumentParser(
        description="Embed doc chunks and load into ChromaDB"
    )
    parser.add_argument(
        "input", nargs="?", default="doc_chunks.jsonl",
        help="JSONL file produced by di-ingest (default: doc_chunks.jsonl)",
    )
    parser.add_argument("-o", "--output", help="Output JSONL (default: overwrites input)")
    parser.add_argument("--collection", default=COLLECTION_NAME,
                        help=f"ChromaDB collection name (default: {COLLECTION_NAME})")
    args = parser.parse_args()
    embed_docs(
        Path(args.input),
        Path(args.output) if args.output else None,
        collection_name=args.collection,
    )


if __name__ == "__main__":
    main()
