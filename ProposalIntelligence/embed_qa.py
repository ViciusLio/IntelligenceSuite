"""pi-embed — embedda le coppie Q&A in ChromaDB.

Particolarità rispetto agli altri moduli: l'embedding è calcolato sulla
**domanda** (``metadata.question``), non sull'intero testo del chunk, così la
ricerca matcha la nuova domanda con le domande passate. Il documento salvato
resta la coppia intera, utile come esempio few-shot in fase di risposta.

Usa l'embedder per-modulo ``PI_EMBED_*`` (vedi config): tipicamente un modello
multilingue, senza disturbare le collezioni code/doc/mentor globali.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from intelligence_core.chunk import chunk_from_jsonl, chunk_to_jsonl
from intelligence_core.config import settings
from intelligence_core.embedder import get_module_embedder
from ProposalIntelligence import COLLECTION_NAME


def _embed_text(chunk: dict) -> str:
    """Testo da embeddare: la domanda (fallback al testo intero)."""
    return chunk.get("metadata", {}).get("question") or chunk["text"]


def embed_qa(
    input_file: Path,
    output_file: Path | None = None,
    incremental: bool = False,
    collection_name: str = COLLECTION_NAME,
) -> list[dict]:
    output_file = output_file or input_file
    embedder = get_module_embedder("pi")

    chunks: list[dict] = []
    with input_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(chunk_from_jsonl(line))

    from intelligence_core.store import ChromaStore
    store = ChromaStore(collection_name=collection_name)

    if incremental:
        chroma_checksums = store.get_checksums()
        to_embed = [
            c for c in chunks
            if chroma_checksums.get(c["id"]) != c.get("checksum", "")
        ]
        jsonl_ids = {c["id"] for c in chunks}
        orphan_ids = [i for i in chroma_checksums if i not in jsonl_ids]
        if orphan_ids:
            store.delete(orphan_ids)
            print(f"  Rimossi {len(orphan_ids)} chunk orfani da ChromaDB")
        print(f"  Incremental: {len(to_embed)}/{len(chunks)} coppie da (ri-)embeddare")
    else:
        to_embed = chunks

    print(f"Embedding {len(to_embed)}/{len(chunks)} coppie Q&A (sulla domanda)...")
    batch_size = settings.embed_batch_size
    for i in range(0, len(to_embed), batch_size):
        batch = to_embed[i: i + batch_size]
        embeddings = embedder.embed([_embed_text(c) for c in batch])
        for chunk, emb in zip(batch, embeddings):
            chunk["embedding"] = emb
        print(f"  batch {i // batch_size + 1}: {len(batch)} coppie")

    with output_file.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(chunk_to_jsonl(c) + "\n")
    print(f"JSONL salvato: {output_file}")

    if to_embed:
        store.add(to_embed)
    print(f"ChromaDB '{collection_name}': {store.count()} coppie totali indicizzate")

    return chunks


def main():
    parser = argparse.ArgumentParser(description="Embedda le coppie Q&A in ChromaDB")
    parser.add_argument("input", nargs="?", default="qa_chunks.jsonl")
    parser.add_argument("-o", "--output", help="Output JSONL (default: sovrascrive input)")
    parser.add_argument("--incremental", action="store_true",
                        help="Salta coppie già indicizzate con checksum invariato")
    parser.add_argument("--collection", default=COLLECTION_NAME)
    args = parser.parse_args()
    embed_qa(
        Path(args.input),
        Path(args.output) if args.output else None,
        incremental=args.incremental,
        collection_name=args.collection,
    )


if __name__ == "__main__":
    main()
