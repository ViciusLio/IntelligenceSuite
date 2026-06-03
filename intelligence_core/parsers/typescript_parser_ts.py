"""Parser TypeScript/JavaScript basato su Tree-sitter."""

from __future__ import annotations

from .treesitter_base import TreeSitterParser


class TypeScriptParser(TreeSitterParser):
    language = "typescript"
    extensions = [".ts", ".tsx"]
    _node_types = [
        "function_declaration",
        "method_definition",
    ]
