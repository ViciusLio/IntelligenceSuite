"""Parser Go basato su Tree-sitter."""

from __future__ import annotations

from .treesitter_base import TreeSitterParser


class GoParser(TreeSitterParser):
    language = "go"
    extensions = [".go"]
    _node_types = [
        "function_declaration",
        "method_declaration",
    ]
