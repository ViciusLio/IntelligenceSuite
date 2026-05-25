"""
IntelligenceSuite — Example 02: Document Intelligence
======================================================
Complete pipeline: ingest → embed → index into ChromaDB → query.

ChromaDB runs embedded (no separate server needed).
Data is persisted to .chroma/ automatically.

Prerequisites
-------------
    pip install "intelligence-suite[pdf,docx,xlsx]"
    ollama serve                         # start Ollama
    ollama pull nomic-embed-text         # embedding model
    ollama pull qwen2.5-coder:7b         # or set LLM_BACKEND=openai / claude

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
    parser.add_argument("--docs", default="./docs", help="Documents folder (default: ./docs)")
    parser.add_argument("--question", default="What are the deployment prerequisites?")
    args = parser.parse_args()

    docs_path = Path(args.docs).resolve()
    print(f"\n{'='*60}")
    print(f"  IntelligenceSuite — Document Intelligence")
    print(f"{'='*60}")
    print(f"  Docs    : {docs_path}")
    print(f"  Question: {args.question}")
    print(f"{'='*60}\n")

    if not docs_path.exists():
        print(f"  ⚠  Folder not found: {docs_path}")
        print("     Create it and add PDF / DOCX / XLSX / TXT / MD files.\n")
        return

    # ── Step 1: Ingest documents ─────────────────────────────────────────────
    print("Step 1/3 — Ingesting documents...")
    from DocIntelligence.ingest_docs import ingest_docs

    chunks = ingest_docs(docs_path, output=Path("doc_chunks.jsonl"))
    print(f"  → {len(chunks)} chunks  →  doc_chunks.jsonl\n")

    if not chunks:
        print("  ⚠  No chunks — check that the folder has supported files (PDF/DOCX/XLSX/TXT/MD)")
        return

    s = chunks[0]
    print(f"  Sample chunk: [{s['type']}] {s['source']}  —  {s['text'][:80].strip()}...\n")

    # ── Step 2: Embed + load into ChromaDB ───────────────────────────────────
    # embed_docs() handles both: writes JSONL and loads into ChromaDB "doc_intelligence"
    # ChromaDB is embedded — no separate server needed, data saved to .chroma/
    print("Step 2/3 — Embedding & indexing into ChromaDB...")
    from DocIntelligence.embed_docs import embed_docs

    embed_docs(Path("doc_chunks.jsonl"))   # → .chroma/doc_intelligence
    print()

    # ── Step 3: Query ────────────────────────────────────────────────────────
    print("Step 3/3 — Querying...\n")
    from intelligence_core.retriever import Retriever
    from intelligence_core.store import ChromaStore
    from intelligence_core.embedder import get_embedder
    from intelligence_core.llm import get_llm_provider

    store     = ChromaStore(collection_name="doc_intelligence")
    retriever = Retriever(embedder=get_embedder(), store=store)
    llm       = get_llm_provider()

    results = retriever.search(args.question, domain="doc", top_k=5)

    print(f"Question: {args.question}\n")
    if not results:
        print("  ⚠  No results — check that embedding succeeded (Ollama running?)")
        return

    print("Top chunks retrieved:")
    for r in results:
        print(f"  [{r.rank}] score={r.score:.3f}  {r.chunk.get('source','')}  ({r.chunk.get('type','')})")

    if llm.is_available():
        print()
        context = "\n\n---\n\n".join(r.chunk["text"] for r in results[:3])
        answer  = llm.generate(args.question, context)
        print(f"Answer ({llm.backend_name}):")
        print(f"  {answer[:500]}")
    else:
        print(f"\n  ⚠  LLM '{llm.backend_name}' not reachable — retrieval results shown above.")

    print(f"\n{'='*60}")
    print("  Done. ChromaDB persisted in .chroma/ — re-query anytime with di-serve")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
