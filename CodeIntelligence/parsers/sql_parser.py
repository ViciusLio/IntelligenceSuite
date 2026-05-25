"""Parser SQL — estrae CREATE TABLE, VIEW, PROCEDURE come chunk leggibili."""

from __future__ import annotations
import re
from pathlib import Path

from intelligence_core.chunk import make_chunk


def can_parse(path: Path) -> bool:
    return path.suffix in {".sql", ".ddl"}


def parse_file(path: Path, root: Path) -> list[dict]:
    """Ritorna chunk da file SQL. Fallback a chunk raw."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    rel = str(path.relative_to(root)).replace("\\", "/")
    stem = rel.replace("/", ".").removesuffix(path.suffix)
    chunks = []

    # TODO: implement full SQL parsing via sqlparse library
    # Pattern: CREATE statements
    create_pattern = re.compile(
        r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW|PROCEDURE|FUNCTION|INDEX)\s+(\w+)",
        re.IGNORECASE | re.MULTILINE,
    )
    for m in create_pattern.finditer(source):
        name = m.group(1)
        snippet = source[m.start(): m.start() + 500]
        kind = re.search(r"TABLE|VIEW|PROCEDURE|FUNCTION|INDEX", m.group(0), re.IGNORECASE)
        kind_str = kind.group(0).capitalize() if kind else "Statement"
        text = (
            f"SQL {kind_str}: {name} (in {rel})\n"
            f"---\n{snippet}"
        )
        chunks.append(make_chunk(
            domain="code", type_="config_block", locator=f"{stem}.{name}",
            text=text[:2000], source=rel, language="sql",
            metadata={"sql_type": kind_str, "name": name},
        ))

    if not chunks:
        preview = source[:2000]
        chunks.append(make_chunk(
            domain="code", type_="file", locator=stem,
            text=f"SQL File: {path.name} (in {rel})\n---\n{preview}",
            source=rel, language="sql",
            metadata={"raw": True},
        ))

    return chunks
