"""Parse JSONL chunks, add embeddings, write back, and load into ChromaDB."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from intelligence_core.chunk import chunk_from_jsonl, chunk_to_jsonl
from intelligence_core.config import settings
from intelligence_core.embedder import get_embedder

COLLECTION_NAME = "code_intelligence"  # base name; runtime uses paths.collection_name("code")


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
    collection_name: str = None,
) -> list[dict]:
    """Full pipeline step: embed chunks and load into ChromaDB.

    Args:
        input_file:       JSONL file produced by ci-parse.
        output_file:      Destination JSONL (default: overwrite input).
        incremental:      Compare chunk checksums with ChromaDB; only embed
                          new or modified chunks and delete orphan IDs whose
                          source files have been removed.
        collection_name:  ChromaDB collection (default: ``code_intelligence``).
    """
    from intelligence_core import paths
    t0 = time.perf_counter()
    collection_name = collection_name or paths.collection_name("code")
    output_file = output_file or input_file
    embedder = get_embedder()

    chunks: list[dict] = []
    with input_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(chunk_from_jsonl(line))

    # ── ChromaDB store (needed for both modes) ───────────────────────────────
    from intelligence_core.store import ChromaStore
    store = ChromaStore(collection_name=collection_name, persist_dir=str(paths.chroma_dir()))

    if incremental:
        # Fetch {id: checksum} for all chunks currently in ChromaDB
        chroma_checksums = store.get_checksums()

        # Chunks to embed: new (not in ChromaDB) or changed (checksum differs)
        to_embed = [
            c for c in chunks
            if chroma_checksums.get(c["id"]) != c.get("checksum", "")
        ]

        # Orphan IDs: exist in ChromaDB but no longer in the JSONL (file deleted)
        jsonl_ids = {c["id"] for c in chunks}
        orphan_ids = [id_ for id_ in chroma_checksums if id_ not in jsonl_ids]
        if orphan_ids:
            store.delete(orphan_ids)
            print(f"  Rimossi {len(orphan_ids)} chunk orfani da ChromaDB")

        skipped = len(chunks) - len(to_embed)
        print(
            f"  Incremental: {len(to_embed)}/{len(chunks)} chunk da (ri-)embeddare"
            + (f", {skipped} invariati" if skipped else "")
        )
    else:
        to_embed = chunks

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
    if to_embed:
        store.add(to_embed)   # upsert only new / changed chunks
    print(f"ChromaDB '{collection_name}': {store.count()} total chunks indexed")

    from intelligence_core.observability import log_ingestion_event
    log_ingestion_event(
        module="code",
        project=getattr(settings, "is_project", "default"),
        total=len(chunks),
        new=len(to_embed),
        skipped=len(chunks) - len(to_embed),
        duration_ms=(time.perf_counter() - t0) * 1000,
        backend=settings.embed_backend,
    )

    return chunks


def incremental_update(input_file: Path, output_file: Path = None) -> list[dict]:
    """Add embeddings only to new/changed chunks (incremental re-index)."""
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
    parser.add_argument(
        "--incremental", action="store_true",
        help=(
            "Salta chunk già indicizzati con checksum invariato. "
            "Rimuove da ChromaDB gli ID orfani (file eliminati)."
        ),
    )
    parser.add_argument("--collection", default=None,
                        help="ChromaDB collection name (default: code_intelligence, prefixed when IS_PROJECT is set)")
    args = parser.parse_args()
    embed_chunks(
        Path(args.input),
        Path(args.output) if args.output else None,
        incremental=args.incremental,
        collection_name=args.collection,
    )


if __name__ == "__main__":
    main()
