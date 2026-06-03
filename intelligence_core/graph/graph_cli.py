"""CLI ci-graph: costruisce e ispeziona il grafo delle dipendenze."""

from __future__ import annotations

import argparse

from .builder import build_graph
from .store import save_graph


def main():
    parser = argparse.ArgumentParser(description="Costruisce il grafo delle dipendenze")
    parser.add_argument("--domain", choices=["code"], default="code")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--top-critical", type=int, default=0)
    args = parser.parse_args()

    print(f"Costruzione grafo per '{args.domain}'...")
    graph = build_graph(args.domain)
    save_graph(graph, args.domain)

    if args.stats:
        import networkx as nx

        print("\nStatistiche:")
        print(f"  Nodi:       {graph.number_of_nodes()}")
        print(f"  Archi:      {graph.number_of_edges()}")
        print(f"  Componenti: {nx.number_weakly_connected_components(graph)}")
        print(f"  Densità:    {nx.density(graph):.5f}")

    if args.top_critical > 0:
        from .retriever import GraphRetriever

        r = GraphRetriever(args.domain)
        critical = r.most_connected(args.top_critical)
        print(f"\nTop {args.top_critical} nodi critici:")
        for i, n in enumerate(critical, 1):
            print(f"  {i:2}. {n['name']:<35} {n['in_degree']} chiamanti")

    print("\nGrafo pronto. Il retriever userà GraphRAG automaticamente.")


if __name__ == "__main__":
    main()
