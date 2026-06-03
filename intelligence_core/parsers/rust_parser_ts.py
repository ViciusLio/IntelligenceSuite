"""Parser Rust basato su Tree-sitter."""

from __future__ import annotations

from .treesitter_base import TreeSitterParser


class RustParser(TreeSitterParser):
    language = "rust"
    extensions = [".rs"]
    # I metodi dentro ``impl`` sono comunque ``function_item`` e vengono
    # raccolti dalla visita ricorsiva: non serve includere ``impl_item``.
    _node_types = [
        "function_item",
    ]
