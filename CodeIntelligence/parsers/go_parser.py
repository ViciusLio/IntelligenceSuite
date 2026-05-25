"""Parser Go — regex best-effort. TODO: tree-sitter per parsing completo."""

from __future__ import annotations
import re
from pathlib import Path

from intelligence_core.chunk import make_chunk


def can_parse(path: Path) -> bool:
    return path.suffix == ".go"


def parse_file(path: Path, root: Path) -> list[dict]:
    """Ritorna chunk da file Go. Fallback a chunk raw."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    rel = str(path.relative_to(root)).replace("\\", "/")
    stem = rel.replace("/", ".").removesuffix(".go")
    chunks = []

    # TODO: implement full parsing via tree-sitter-go
    # Pattern: function and method declarations
    fn_pattern = re.compile(
        r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\([^)]*\)", re.MULTILINE
    )
    for m in fn_pattern.finditer(source):
        name = m.group(1)
        snippet = source[m.start(): m.start() + 400]
        text = (
            f"Function: {name} (in {rel})\n"
            f"Signature: {m.group(0).strip()}\n"
            f"Body preview:\n{snippet}"
        )
        chunks.append(make_chunk(
            domain="code", type_="function", locator=f"{stem}.{name}",
            text=text[:2000], source=rel, language="go",
            metadata={"raw": True},
        ))

    # Pattern: struct declarations
    struct_pattern = re.compile(r"^type\s+(\w+)\s+struct\b", re.MULTILINE)
    for m in struct_pattern.finditer(source):
        name = m.group(1)
        snippet = source[m.start(): m.start() + 300]
        text = f"Struct: {name} (in {rel})\n{snippet}"
        chunks.append(make_chunk(
            domain="code", type_="class", locator=f"{stem}.{name}",
            text=text[:2000], source=rel, language="go",
            metadata={"raw": True},
        ))

    if not chunks:
        preview = source[:2000]
        chunks.append(make_chunk(
            domain="code", type_="file", locator=stem,
            text=f"File: {path.name} (in {rel})\n---\n{preview}",
            source=rel, language="go",
            metadata={"raw": True},
        ))

    return chunks
