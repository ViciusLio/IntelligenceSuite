"""Query sul grafo: impatto, dipendenze, nodi critici, espansione GraphRAG."""

from __future__ import annotations

import networkx as nx

from .store import load_graph


class GraphRetriever:
    def __init__(self, domain: str = "code"):
        self.domain = domain
        self._graph: nx.DiGraph | None = None

    @property
    def graph(self) -> nx.DiGraph:
        if self._graph is None:
            self._graph = load_graph(self.domain)
        return self._graph

    def find_node(self, name: str) -> str | None:
        for node_id, data in self.graph.nodes(data=True):
            if data.get("name") == name:
                return node_id
        return None

    def who_calls(self, function_name: str, depth: int = 1) -> list[dict]:
        node_id = self.find_node(function_name)
        if not node_id:
            return []
        reverse = self.graph.reverse()
        callers = []
        for caller_id in nx.ego_graph(reverse, node_id, radius=depth).nodes():
            if caller_id == node_id:
                continue
            data = self.graph.nodes[caller_id]
            callers.append({
                "name": data.get("name", ""),
                "file": data.get("file", ""),
                "line": data.get("line", 0),
                "chunk_id": data.get("chunk_id", ""),
            })
        return callers

    def impact_analysis(self, function_name: str, depth: int = 3) -> dict:
        node_id = self.find_node(function_name)
        if not node_id:
            return {"error": f"'{function_name}' non trovata nel grafo"}

        direct = self.who_calls(function_name, depth=1)
        all_affected = self.who_calls(function_name, depth=depth)
        affected_files = list({
            item["file"] for item in all_affected if item["file"]
        })

        return {
            "function": function_name,
            "direct_callers": direct,
            "total_affected": len(all_affected),
            "affected_files": affected_files,
            "risk_level": _risk_level(len(all_affected)),
        }

    def dependencies_of(self, function_name: str, depth: int = 2) -> list[dict]:
        node_id = self.find_node(function_name)
        if not node_id:
            return []
        deps = []
        for dep_id in nx.ego_graph(self.graph, node_id, radius=depth).nodes():
            if dep_id == node_id:
                continue
            data = self.graph.nodes[dep_id]
            deps.append({
                "name": data.get("name", ""),
                "file": data.get("file", ""),
                "chunk_id": data.get("chunk_id", ""),
            })
        return deps

    def most_connected(self, top_k: int = 10) -> list[dict]:
        in_degrees = sorted(
            self.graph.in_degree(), key=lambda x: x[1], reverse=True
        )[:top_k]
        result = []
        for node_id, degree in in_degrees:
            data = self.graph.nodes[node_id]
            result.append({
                "name": data.get("name", ""),
                "file": data.get("file", ""),
                "in_degree": degree,
                "chunk_id": data.get("chunk_id", ""),
            })
        return result

    def expand_context(self, chunk_ids: list[str], depth: int = 1) -> list[str]:
        """GraphRAG: vicini strutturali (callers + callees) dei chunk trovati.

        Usa il grafo non orientato così l'espansione include sia le dipendenze
        (archi uscenti) sia i chiamanti (archi entranti): per un nodo molto
        chiamato i vicini utili stanno quasi tutti sugli archi entranti.
        """
        undirected = self.graph.to_undirected(as_view=True)
        seed = set(chunk_ids)
        additional = set()
        for chunk_id in chunk_ids:
            if chunk_id not in undirected:
                continue
            for neighbor_id in nx.ego_graph(undirected, chunk_id, radius=depth).nodes():
                if neighbor_id not in seed:
                    additional.add(neighbor_id)
        return list(additional)


def _risk_level(count: int) -> str:
    if count == 0:
        return "none"
    if count <= 3:
        return "low"
    if count <= 10:
        return "medium"
    return "high"
