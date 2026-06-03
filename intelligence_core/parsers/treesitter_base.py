"""Classe base per i parser Tree-sitter.

Ogni linguaggio eredita da questa e definisce ``language``, ``extensions``
e ``_node_types``. La costruzione del parser usa ``tree_sitter_language_pack``
per ottenere la grammatica e l'API standard di ``tree_sitter`` per il parsing
(il ``get_parser`` del pack espone un binding incompatibile con tree-sitter>=0.25,
quindi costruiamo noi il ``Parser`` da ``get_language``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from .base import BaseParser, ChunkDict

logger = logging.getLogger(__name__)

# Tipi di nodo che rappresentano una chiamata, attraverso i vari linguaggi.
_CALL_NODE_TYPES = {
    "call_expression",       # ts/js, rust, go
    "function_call",
    "invocation_expression",
    "method_invocation",     # java
    "call",                  # python-ish grammars
}


class TreeSitterParser(BaseParser):
    language: str = ""
    extensions: list[str] = []
    _node_types: list[str] = []

    def __init__(self):
        try:
            from tree_sitter import Parser
            from tree_sitter_language_pack import get_language
        except ImportError as exc:
            raise ImportError(
                "tree-sitter-language-pack non installato. "
                "Esegui: pip install 'intelligence-suite[multilang]'"
            ) from exc
        try:
            self._parser = Parser(get_language(self.language))
        except Exception as exc:
            raise RuntimeError(
                f"Parser Tree-sitter per '{self.language}' non disponibile: {exc}"
            ) from exc

    def parse_file(self, path: Path) -> list[ChunkDict]:
        try:
            source = path.read_bytes()
            tree = self._parser.parse(source)
            return self._extract_chunks(tree, path, source)
        except Exception as exc:
            logger.warning("Errore parsing %s: %s", path, exc)
            return []

    def _extract_chunks(self, tree, path: Path, source: bytes) -> list[ChunkDict]:
        chunks: list[ChunkDict] = []
        self._visit_node(tree.root_node, path, source, chunks)
        return chunks

    def _visit_node(self, node, path: Path, source: bytes, chunks: list) -> None:
        if node.type in self._node_types:
            chunk = self._node_to_chunk(node, path, source)
            if chunk:
                chunks.append(chunk)
        for child in node.children:
            self._visit_node(child, path, source, chunks)

    def _node_to_chunk(self, node, path: Path, source: bytes) -> ChunkDict | None:
        try:
            name = self._extract_name(node, source)
            text = source[node.start_byte:node.end_byte].decode(
                "utf-8", errors="replace"
            )
            calls = self._extract_calls(node, source)
            return {
                "id": f"code::function::{path}::{name}",
                "text": text,
                "type": "function",
                "source": str(path),
                "domain": "code",
                "metadata": {
                    "name": name,
                    "line": node.start_point[0] + 1,
                    "calls": calls,
                    "imports": [],
                    "bases": [],
                    "language": self.language,
                },
            }
        except Exception as exc:
            logger.warning("Errore conversione nodo: %s", exc)
            return None

    def _extract_name(self, node, source: bytes) -> str:
        name_node = node.child_by_field_name("name")
        if name_node:
            return source[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )
        return f"anonymous_{node.start_point[0]}"

    def _extract_calls(self, node, source: bytes) -> list[str]:
        calls: list[str] = []
        self._find_calls(node, source, calls)
        return sorted(set(calls))

    def _find_calls(self, node, source: bytes, calls: list) -> None:
        if node.type in _CALL_NODE_TYPES:
            func_node = (
                node.child_by_field_name("function")
                or node.child_by_field_name("name")
            )
            if func_node:
                raw = source[func_node.start_byte:func_node.end_byte].decode(
                    "utf-8", errors="replace"
                ).strip()
                # Per chiamate qualificate (obj.method, pkg.Func) tieni l'ultimo segmento.
                name = raw.split(".")[-1].split("::")[-1]
                if name and name.isidentifier():
                    calls.append(name)
        for child in node.children:
            self._find_calls(child, source, calls)
