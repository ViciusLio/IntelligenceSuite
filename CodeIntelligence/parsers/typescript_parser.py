"""Parser TypeScript/JavaScript — regex + pattern matching, best-effort."""

from __future__ import annotations
import re
from pathlib import Path

from intelligence_core.chunk import make_chunk


def can_parse(path: Path) -> bool:
    return path.suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs"}


def parse_file(path: Path, root: Path) -> list[dict]:
    """Ritorna chunk da file TS/JS. Fallback a chunk raw."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    rel = str(path.relative_to(root)).replace("\\", "/")
    stem = rel.replace("/", ".").removesuffix(path.suffix)
    chunks = []

    # TODO: implement full AST parsing via tree-sitter or @typescript-eslint/parser
    # Pattern: function declarations
    fn_pattern = re.compile(
        r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\([^)]*\)[^{]*\{",
        re.MULTILINE,
    )
    for m in fn_pattern.finditer(source):
        name = m.group(1)
        snippet = source[m.start(): m.start() + 300]
        text = (
            f"Function: {name} (in {rel})\n"
            f"Signature: {m.group(0).strip()}\n"
            f"Body preview:\n{snippet}"
        )
        chunks.append(make_chunk(
            domain="code", type_="function", locator=f"{stem}.{name}",
            text=text[:2000], source=rel, language="typescript",
            metadata={"raw": True},
        ))

    # Pattern: class declarations
    class_pattern = re.compile(r"(?:export\s+)?class\s+(\w+)", re.MULTILINE)
    for m in class_pattern.finditer(source):
        name = m.group(1)
        snippet = source[m.start(): m.start() + 300]
        text = f"Class: {name} (in {rel})\nSnippet:\n{snippet}"
        chunks.append(make_chunk(
            domain="code", type_="class", locator=f"{stem}.{name}",
            text=text[:2000], source=rel, language="typescript",
            metadata={"raw": True},
        ))

    if not chunks:
        preview = source[:2000]
        chunks.append(make_chunk(
            domain="code", type_="file", locator=stem,
            text=f"File: {path.name} (in {rel})\n---\n{preview}",
            source=rel, language="typescript",
            metadata={"raw": True},
        ))

    return chunks
