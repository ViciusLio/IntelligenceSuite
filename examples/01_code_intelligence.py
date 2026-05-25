"""
IntelligenceSuite — Example 01: Code Intelligence
==================================================
Parse a repository, inspect the resulting chunks,
then query the codebase with a natural-language question.

Prerequisites
-------------
    pip install intelligence-suite
    ollama pull qwen2.5-coder:7b        # or set LLM_BACKEND=openai / claude

Run
---
    python examples/01_code_intelligence.py
    python examples/01_code_intelligence.py --repo /path/to/your/repo
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to the repository to index (default: current directory)",
    )
    parser.add_argument(
        "--question",
        default="Where is authentication handled?",
        help="Question to ask about the codebase",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    print(f"\n{'='*60}")
    print(f"  IntelligenceSuite — Code Intelligence")
    print(f"{'='*60}")
    print(f"  Repo : {repo_path}")
    print(f"  Query: {args.question}")
    print(f"{'='*60}\n")

    # ── Step 1: Parse repository into chunks ────────────────────────────────
    print("Step 1/3 — Parsing repository...")
    from CodeIntelligence.parse_repo import parse_repo

    chunks = parse_repo(repo_path, output=Path("chunks.jsonl"))
    print(f"  → {len(chunks)} chunks extracted to chunks.jsonl\n")

    # Show a sample chunk
    if chunks:
        sample = chunks[0]
        print("Sample chunk:")
        print(f"  id     : {sample['id']}")
        print(f"  type   : {sample['type']}")
        print(f"  source : {sample['source']}")
        print(f"  text   : {sample['text'][:120].strip()}...")
        print()

    # ── Step 2: Check LLM backend ───────────────────────────────────────────
    print("Step 2/3 — Checking LLM backend...")
    from intelligence_core.llm import get_llm_provider

    llm = get_llm_provider()
    available = llm.is_available()
    print(f"  backend  : {llm.backend_name}")
    print(f"  available: {available}")
    if not available:
        print(
            "\n  ⚠  LLM not reachable. For Ollama: make sure it is running and the model is pulled.\n"
            "     Switch backend:  LLM_BACKEND=openai  or  LLM_BACKEND=claude  in .env\n"
            "     Continuing — will show retrieval results only.\n"
        )

    # ── Step 3: Embed + query ───────────────────────────────────────────────
    print("Step 3/3 — Embedding & querying...\n")
    from CodeIntelligence.embed_chunks import embed_chunks
    from intelligence_core.retriever import Retriever
    from intelligence_core.store import ChromaStore
    from intelligence_core.embedder import get_embedder

    embed_chunks(Path("chunks.jsonl"))

    store     = ChromaStore(collection_name="code_intelligence")
    retriever = Retriever(embedder=get_embedder(), store=store)

    results = retriever.search(args.question, domain="code", top_k=5)

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
    print("  Done. Chunks saved to chunks.jsonl")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
