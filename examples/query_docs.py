"""Demo DocIntelligence — esegue query sui documenti aziendali indicizzati."""

from __future__ import annotations
import argparse

from intelligence_core.embedder import get_embedder
from intelligence_core.store import ChromaStore
from intelligence_core.retriever import Retriever

DEMO_QUERIES = [
    "Come ottenere un token API?",
    "Cosa fare se il deploy fallisce entro 30 minuti?",
    "Perché pgvector invece di Pinecone?",
]


def main():
    parser = argparse.ArgumentParser(description="Demo DocIntelligence RAG")
    parser.add_argument("--docs", default="./docs", help="Path ai documenti indicizzati")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    retriever = Retriever(embedder=get_embedder(), store=ChromaStore("doc_intelligence"))
    print(f"Chunk indicizzati: {retriever.store.count()}")
    print()

    for query in DEMO_QUERIES:
        print(f"Q: {query}")
        results = retriever.search(query, top_k=args.top_k, domain="doc")
        if not results:
            print("  [Nessun risultato — indicizza prima con di-ingest e di-embed]")
        for r in results:
            print(f"  [{r.rank}] score={r.score:.3f} | {r.chunk['id']}")
            print(f"      {r.chunk['text'][:120].replace(chr(10), ' ')}...")
        print()


if __name__ == "__main__":
    main()
