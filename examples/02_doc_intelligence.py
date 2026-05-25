"""
IntelligenceSuite — Example 02: Document Intelligence
======================================================
Ingest a folder of company documents (PDF, DOCX, XLSX, TXT, MD),
inspect the chunks, and query them with a natural-language question.

Prerequisites
-------------
    pip install "intelligence-suite[pdf,docx,xlsx]"
    ollama pull qwen2.5-coder:7b        # or set LLM_BACKEND=openai / claude

Run
---
    python examples/02_doc_intelligence.py --docs /path/to/docs
    python examples/02_doc_intelligence.py --docs /path/to/docs --question "What are the deploy prerequisites?"
"""

from __future__ import annotations
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--docs",
        default="./docs",
        help="Path to the documents folder (default: ./docs)",
    )
    parser.add_argument(
        "--question",
        default="What are the deployment prerequisites?",
        help="Question to ask about the documents",
    )
    args = parser.parse_args()

    docs_path = Path(args.docs).resolve()

    print(f"\n{'='*60}")
    print(f"  IntelligenceSuite — Document Intelligence")
    print(f"{'='*60}")
    print(f"  Docs : {docs_path}")
    print(f"  Query: {args.question}")
    print(f"{'='*60}\n")

    if not docs_path.exists():
        print(f"  ⚠  Folder not found: {docs_path}")
        print("     Create it and add PDF / DOCX / XLSX / TXT / MD files, then re-run.\n")
        return

    # ── Step 1: Ingest documents ─────────────────────────────────────────────
    print("Step 1/3 — Ingesting documents...")
    from DocIntelligence.ingest_docs import ingest_docs

    chunks = ingest_docs(docs_path, output=Path("doc_chunks.jsonl"))
    print(f"  → {len(chunks)} chunks extracted to doc_chunks.jsonl\n")

    if not chunks:
        print("  ⚠  No chunks produced. Check that the folder contains supported files.")
        return

    # Show a sample chunk
    sample = chunks[0]
    print("Sample chunk:")
    print(f"  id     : {sample['id']}")
    print(f"  type   : {sample['type']}")
    print(f"  source : {sample['source']}")
    print(f"  text   : {sample['text'][:150].strip()}...")
    print()

    # ── Step 2: Check LLM backend ────────────────────────────────────────────
    print("Step 2/3 — Checking LLM backend...")
    from intelligence_core.llm import get_llm_provider

    llm       = get_llm_provider()
    available = llm.is_available()
    print(f"  backend  : {llm.backend_name}")
    print(f"  available: {available}")
    if not available:
        print(
            "\n  ⚠  LLM not reachable. Continuing — will show retrieval results only.\n"
        )

    # ── Step 3: Embed + query ─────────────────────────────────────────────────
    print("Step 3/3 — Embedding & querying...\n")
    from DocIntelligence.embed_docs import embed_docs
    from intelligence_core.retriever import Retriever
    from intelligence_core.store import ChromaStore
    from intelligence_core.embedder import get_embedder

    embed_docs(Path("doc_chunks.jsonl"))

    store     = ChromaStore(collection_name="doc_intelligence")
    retriever = Retriever(embedder=get_embedder(), store=store)

    results = retriever.search(args.question, domain="doc", top_k=5)

    print(f"Question: {args.question}\n")
    print("Top retrieved chunks:")
    for r in results:
        print(f"  [{r.rank}] score={r.score:.3f}  {r.chunk.get('source','')}  ({r.chunk.get('type','')})")

    if available and results:
        print()
        context = "\n\n---\n\n".join(r.chunk["text"] for r in results[:3])
        answer  = llm.generate(args.question, context)
        print("Answer:")
        print(f"  {answer[:600]}")

    print(f"\n{'='*60}")
    print("  Done. Chunks saved to doc_chunks.jsonl")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
