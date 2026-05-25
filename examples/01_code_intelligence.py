"""
IntelligenceSuite — Example 01: Code Intelligence
==================================================
Complete pipeline: parse → embed → index into ChromaDB → query.

ChromaDB runs embedded (no separate server needed).
Data is persisted to .chroma/ automatically.

Prerequisites
-------------
    pip install intelligence-suite
    ollama serve                         # start Ollama
    ollama pull nomic-embed-text         # embedding model
    ollama pull qwen2.5-coder:7b         # or set LLM_BACKEND=openai / claude

Run
---
    python examples/01_code_intelligence.py
    python examples/01_code_intelligence.py --repo /path/to/your/repo
    python examples/01_code_intelligence.py --question "How does authentication work?"
"""

from __future__ import annotations
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".", help="Repository to index (default: current dir)")
    parser.add_argument("--question", default="Where is authentication handled?")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    print(f"\n{'='*60}")
    print(f"  IntelligenceSuite — Code Intelligence")
    print(f"{'='*60}")
    print(f"  Repo    : {repo_path}")
    print(f"  Question: {args.question}")
    print(f"{'='*60}\n")

    # ── Step 1: Parse repository ─────────────────────────────────────────────
    print("Step 1/3 — Parsing repository...")
    from CodeIntelligence.parse_repo import parse_repo

    chunks = parse_repo(repo_path, output=Path("chunks.jsonl"))
    print(f"  → {len(chunks)} chunks  →  chunks.jsonl\n")

    if chunks:
        s = chunks[0]
        print(f"  Sample chunk: [{s['type']}] {s['source']}  —  {s['text'][:80].strip()}...\n")

    # ── Step 2: Embed + load into ChromaDB ───────────────────────────────────
    # embed_chunks() handles both: writes JSONL and loads into ChromaDB "code_intelligence"
    # ChromaDB is embedded — no separate server needed, data saved to .chroma/
    print("Step 2/3 — Embedding & indexing into ChromaDB...")
    from CodeIntelligence.embed_chunks import embed_chunks

    embed_chunks(Path("chunks.jsonl"))   # → .chroma/code_intelligence
    print()

    # ── Step 3: Query ────────────────────────────────────────────────────────
    print("Step 3/3 — Querying...\n")
    from intelligence_core.retriever import Retriever
    from intelligence_core.store import ChromaStore
    from intelligence_core.embedder import get_embedder
    from intelligence_core.llm import get_llm_provider

    store     = ChromaStore(collection_name="code_intelligence")
    retriever = Retriever(embedder=get_embedder(), store=store)
    llm       = get_llm_provider()

    results = retriever.search(args.question, domain="code", top_k=5)

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
        print("     Start Ollama or set LLM_BACKEND=openai / claude in .env")

    print(f"\n{'='*60}")
    print("  Done. ChromaDB persisted in .chroma/ — re-query anytime with ci-serve")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
