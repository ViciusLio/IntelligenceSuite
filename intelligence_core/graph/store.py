"""Persistenza del grafo su disco in formato JSON (node-link)."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

GRAPH_DIR = Path.home() / ".intelligence_suite" / "graph"


def save_graph(graph: nx.DiGraph, domain: str = "code") -> Path:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    path = GRAPH_DIR / f"{domain}_graph.json"
    data = json_graph.node_link_data(graph, edges="links")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    size_mb = path.stat().st_size / 1024 / 1024
    print(f"Grafo salvato: {path} ({size_mb:.1f} MB)")
    return path


def load_graph(domain: str = "code") -> nx.DiGraph:
    path = GRAPH_DIR / f"{domain}_graph.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Grafo non trovato. Esegui: ci-graph --domain {domain}"
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return json_graph.node_link_graph(data, directed=True, edges="links")


def graph_exists(domain: str = "code") -> bool:
    return (GRAPH_DIR / f"{domain}_graph.json").exists()
