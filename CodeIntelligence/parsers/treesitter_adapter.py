"""Adapter che espone i parser Tree-sitter (intelligence_core.parsers) con
l'interfaccia modulare attesa dal registry CodeIntelligence.

I parser strutturali vivono in ``intelligence_core/parsers`` come classi.
Qui li avvolgiamo in funzioni ``can_parse(path)`` / ``parse_file(path, root)``
che riemettono i chunk via ``make_chunk``, mantenendo lo schema unificato
(id ``domain::type::locator``, metadata con ``calls``/``imports``/``bases``).

L'import dei parser Tree-sitter avviene a livello di modulo: se la dipendenza
opzionale ``[multilang]`` non è installata, l'import fallisce e il registry
ricade automaticamente sui parser regex esistenti (zero breaking changes).
"""

from __future__ import annotations

from pathlib import Path

from intelligence_core.chunk import make_chunk
from intelligence_core.parsers.typescript_parser_ts import TypeScriptParser
from intelligence_core.parsers.go_parser_ts import GoParser
from intelligence_core.parsers.java_parser_ts import JavaParser
from intelligence_core.parsers.rust_parser_ts import RustParser

# Istanze riusabili (l'__init__ carica il binding Tree-sitter una sola volta).
_PARSERS = [
    TypeScriptParser(),
    GoParser(),
    JavaParser(),
    RustParser(),
]

_EXTENSIONS = {ext for p in _PARSERS for ext in p.extensions}


def can_parse(path: Path) -> bool:
    return path.suffix.lower() in _EXTENSIONS


def _parser_for(path: Path):
    for parser in _PARSERS:
        if parser.can_parse(path):
            return parser
    return None


def parse_file(path: Path, root: Path) -> list[dict]:
    """Estrae chunk strutturali via Tree-sitter e li riemette in schema unificato."""
    parser = _parser_for(path)
    if parser is None:
        return []

    raw_chunks = parser.parse_file(path)
    if not raw_chunks:
        return []

    rel = str(path.relative_to(root)).replace("\\", "/")
    stem = rel.replace("/", ".").removesuffix(path.suffix)

    chunks = []
    for raw in raw_chunks:
        meta = raw.get("metadata", {})
        name = meta.get("name", "anonymous")
        chunks.append(make_chunk(
            domain="code",
            type_="function",
            locator=f"{stem}.{name}",
            text=raw.get("text", "")[:2000],
            source=rel,
            language=meta.get("language", parser.language),
            metadata={
                "name": name,
                "line": meta.get("line", 0),
                "calls": meta.get("calls", []),
                "imports": meta.get("imports", []),
                "bases": meta.get("bases", []),
                "language": meta.get("language", parser.language),
            },
        ))
    return chunks
