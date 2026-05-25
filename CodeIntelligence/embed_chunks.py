"""Parse JSONL chunks, add embeddings, write back, and load into ChromaDB."""

from __future__ import annotations
import argparse
from pathlib import Path

from intelligence_core.chunk import chunk_from_jsonl, chunk_to_jsonl
from intelligence_core.embedder import get_embedder
from intelligence_core.config import settings

COLLECTION_NAME = "code_intelligence"


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
        print("       3.  Re-run:  ci-embed")
        print("     Or switch to a local CPU model: EMBED_BACKEND=st in .env\n")


def embed_chunks(
    input_file: Path,
    output_file: Path = None,
    incremental: bool = False,
    collection_name: str = COLLECTION_NAME,
) -> list[dict]:
    """
    Full pipeline step:
      1. Read chunks from JSONL
      2. Compute embeddings (Ollama / SentenceTransformer / Voyage)
      3. Write updated JSONL
      4. Upsert into ChromaDB — collection ready for ci-serve

    Args:
        input_file:       JSONL file produced by ci-parse.
        output_file:      Destination JSONL (default: overwrite input).
        incremental:      Skip chunks that already have an embedding.
        collection_name:  ChromaDB collection (default: ``code_intelligence``).
    """
    output_file = output_file or input_file
    embedder = get_embedder()

    chunks: list[dict] = []
    with input_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(chunk_from_jsonl(line))

    to_embed = [c for c in chunks if not incremental or not c.get("embedding")]
    print(f"Embedding {len(to_embed)}/{len(chunks)} chunks...")

    batch_size = settings.embed_batch_size
    for i in range(0, len(to_embed), batch_size):
        batch      = to_embed[i: i + batch_size]
        embeddings = embedder.embed([c["text"] for c in batch])
        for chunk, emb in zip(batch, embeddings):
            chunk["embedding"] = emb
        print(f"  batch {i // batch_size + 1}: {len(batch)} chunks embedded")

    _warn_zero_embeddings(to_embed)

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


def incremental_update(input_file: Path, output_file: Path = None) -> list[dict]:
    """Add embeddings only to chunks without one (incremental re-index)."""
    return embed_chunks(input_file, output_file, incremental=True)


def main():
    parser = argparse.ArgumentParser(
        description="Embed code chunks and load into ChromaDB"
    )
    parser.add_argument(
        "input", nargs="?", default="chunks.jsonl",
        help="JSONL file produced by ci-parse (default: chunks.jsonl)",
    )
    parser.add_argument("-o", "--output", help="Output JSONL (default: overwrites input)")
    parser.add_argument("--incremental", action="store_true",
                        help="Skip chunks that already have embeddings")
    parser.add_argument("--collection", default=COLLECTION_NAME,
                        help=f"ChromaDB collection name (default: {COLLECTION_NAME})")
    args = parser.parse_args()
    embed_chunks(
        Path(args.input),
        Path(args.output) if args.output else None,
        incremental=args.incremental,
        collection_name=args.collection,
    )


if __name__ == "__main__":
    main()
