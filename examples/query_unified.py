"""Demo query cross-domain: stessa query su codice e documenti."""

from __future__ import annotations
import argparse

from intelligence_core.embedder import get_embedder
from intelligence_core.store import ChromaStore
from intelligence_core.retriever import Retriever

DEMO_QUERIES = [
    "Come funziona il rate limiting?",
    "Procedure di rollback in caso di errore",
]


def main():
    parser = argparse.ArgumentParser(description="Demo query cross-domain")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    embedder = get_embedder()
    code_retriever = Retriever(embedder=embedder, store=ChromaStore("code_intelligence"))
    doc_retriever  = Retriever(embedder=embedder, store=ChromaStore("doc_intelligence"))

    print(f"Chunk code: {code_retriever.store.count()} | doc: {doc_retriever.store.count()}")
    print()

    for query in DEMO_QUERIES:
        print(f"═══ Q: {query}")

        print("  [CODE]")
        code_results = code_retriever.search(query, top_k=args.top_k, domain="code")
        if not code_results:
            print("    [Nessun risultato]")
        for r in code_results:
            print(f"    [{r.rank}] {r.chunk['id']} (score={r.score:.3f})")
            print(f"         {r.chunk['text'][:100].replace(chr(10), ' ')}...")

        print("  [DOC]")
        doc_results = doc_retriever.search(query, top_k=args.top_k, domain="doc")
        if not doc_results:
            print("    [Nessun risultato]")
        for r in doc_results:
            print(f"    [{r.rank}] {r.chunk['id']} (score={r.score:.3f})")
            print(f"         source: {r.chunk.get('source', '?')}")
            print(f"         {r.chunk['text'][:100].replace(chr(10), ' ')}...")
        print()


if __name__ == "__main__":
    main()
