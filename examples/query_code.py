"""Demo CodeIntelligence — esegue query sul codice sorgente indicizzato."""

from __future__ import annotations
import argparse
from pathlib import Path

from intelligence_core.embedder import get_embedder
from intelligence_core.store import ChromaStore
from intelligence_core.retriever import Retriever

DEMO_QUERIES = [
    "Dove viene gestita l'autenticazione JWT?",
    "Come funziona l'escalation da locale a Claude?",
    "Come si aggiunge un nuovo parser di linguaggio?",
]


def main():
    parser = argparse.ArgumentParser(description="Demo CodeIntelligence RAG")
    parser.add_argument("--repo", default=".", help="Path alla repo indicizzata")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    retriever = Retriever(embedder=get_embedder(), store=ChromaStore("code_intelligence"))
    print(f"Chunk indicizzati: {retriever.store.count()}")
    print()

    for query in DEMO_QUERIES:
        print(f"Q: {query}")
        results = retriever.search(query, top_k=args.top_k, domain="code")
        if not results:
            print("  [Nessun risultato — indicizza prima con ci-parse e ci-embed]")
        for r in results:
            print(f"  [{r.rank}] score={r.score:.3f} | {r.chunk['id']}")
            print(f"      {r.chunk['text'][:120].replace(chr(10), ' ')}...")
        print()


if __name__ == "__main__":
    main()
