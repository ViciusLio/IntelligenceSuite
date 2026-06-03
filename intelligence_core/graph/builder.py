"""Costruisce il grafo orientato delle dipendenze dai chunk JSONL."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx


def build_graph(domain: str = "code") -> nx.DiGraph:
    chunks_path = _get_chunks_path(domain)
    if not chunks_path.exists():
        raise FileNotFoundError(
            f"Chunks non trovati per '{domain}' ({chunks_path}). "
            f"Esegui ci-parse e ci-embed."
        )

    with open(chunks_path, encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]

    graph = nx.DiGraph()

    # Prima passata: nodi (function, class, module).
    for chunk in chunks:
        if chunk.get("type") not in ("function", "class", "module"):
            continue
        node_id = chunk["id"]
        metadata = chunk.get("metadata", {})
        graph.add_node(
            node_id,
            name=metadata.get("name") or _name_from_id(node_id),
            type=chunk.get("type", ""),
            file=chunk.get("source", ""),
            line=metadata.get("line_start", metadata.get("line", 0)),
            chunk_id=node_id,
            domain=chunk.get("domain", domain),
        )

    # Indice nome -> node_id per costruire gli archi.
    node_by_name: dict[str, str] = {}
    for node_id, data in graph.nodes(data=True):
        name = data.get("name", "")
        if name and name not in node_by_name:
            node_by_name[name] = node_id

    # Seconda passata: archi.
    for chunk in chunks:
        if chunk.get("type") not in ("function", "class"):
            continue
        source_id = chunk["id"]
        if source_id not in graph:
            continue
        metadata = chunk.get("metadata", {})

        for called in metadata.get("calls", []):
            target_id = node_by_name.get(called)
            if target_id and target_id != source_id:
                graph.add_edge(source_id, target_id, relation="CALLS")

        for imported in metadata.get("imports", []):
            target_id = node_by_name.get(imported)
            if target_id:
                graph.add_edge(source_id, target_id, relation="IMPORTS")

        for base in metadata.get("bases", []):
            target_id = node_by_name.get(base)
            if target_id:
                graph.add_edge(source_id, target_id, relation="INHERITS_FROM")

    print(
        f"Grafo costruito: {graph.number_of_nodes()} nodi, "
        f"{graph.number_of_edges()} archi"
    )
    return graph


def _name_from_id(node_id: str) -> str:
    """Deriva un nome leggibile dall'ID (domain::type::locator)."""
    locator = node_id.split("::")[-1]
    return locator.split(".")[-1]


def _get_chunks_path(domain: str) -> Path:
    from intelligence_core.evaluation.paths import get_chunks_path

    return get_chunks_path(domain)
