"""Parser Java basato su Tree-sitter."""

from __future__ import annotations

from .treesitter_base import TreeSitterParser


class JavaParser(TreeSitterParser):
    language = "java"
    extensions = [".java"]
    _node_types = [
        "method_declaration",
        "constructor_declaration",
    ]
