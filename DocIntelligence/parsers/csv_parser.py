"""Parser CSV — un chunk sezione (schema) + un chunk tabella (anteprima righe).

Solo stdlib (``csv``): nessuna dipendenza nuova. Best-effort: in caso di errore
ritorna un chunk raw così la pipeline non si interrompe mai.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from intelligence_core.chunk import make_chunk

_MAX_PREVIEW_ROWS = 20
_MAX_TABLE_CHARS = 7500


def can_parse(path: Path) -> bool:
    return path.suffix.lower() in {".csv", ".tsv"}


def parse_file(path: Path, root: Path) -> list[dict]:
    """Ritorna chunk da CSV/TSV. Fallback a chunk raw in caso di errore."""
    rel = str(path.relative_to(root)).replace("\\", "/")
    stem = path.stem
    try:
        return _parse_csv(path, rel, stem)
    except Exception as e:
        return [make_chunk(
            domain="doc", type_="section", locator=_sanitize(stem),
            text=f"File: {path.name} (in {rel})\n---\n[Errore parsing CSV: {e}]",
            source=rel, language="csv",
            metadata={"page_start": 1, "page_end": 1, "heading_path": [stem]},
        )]


def _parse_csv(path: Path, rel: str, stem: str) -> list[dict]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        sample = f.read(8192)
        f.seek(0)
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            pass
        rows = [r for r in csv.reader(f, delimiter=delimiter)
                if any(str(v).strip() for v in r)]

    if not rows:
        return [make_chunk(
            domain="doc", type_="section", locator=_sanitize(stem),
            text=f"File: {path.name} (in {rel})\n---\n[CSV vuoto]",
            source=rel, language="csv",
            metadata={"page_start": 1, "page_end": 1, "heading_path": [stem]},
        )]

    header = [str(v).strip() for v in rows[0]]
    data_rows = rows[1:]

    chunks = [make_chunk(
        domain="doc", type_="section", locator=_sanitize(stem),
        text=(
            f"Section: {path.name} (in {rel})\n"
            f"Path: {stem}\n---\n"
            f"Tabella CSV con {len(data_rows)} righe e {len(header)} colonne.\n"
            f"Colonne: {', '.join(header)}"
        ),
        source=rel, language="csv",
        metadata={
            "page_start": 1, "page_end": 1, "heading_path": [stem],
            "columns": header, "row_count": len(data_rows),
        },
    )]

    if data_rows:
        lines = [
            f"Table: {path.name} (in {rel})",
            f"Columns: {', '.join(header)}",
            "---",
            " | ".join(header),
        ]
        for row in data_rows[:_MAX_PREVIEW_ROWS]:
            lines.append(" | ".join(str(v) for v in row))
        if len(data_rows) > _MAX_PREVIEW_ROWS:
            lines.append(f"... [{len(data_rows)} righe totali]")
        chunks.append(make_chunk(
            domain="doc", type_="table", locator=f"{_sanitize(stem)}.table",
            text="\n".join(lines)[:_MAX_TABLE_CHARS],
            source=rel, language="csv",
            metadata={
                "page_start": 1, "page_end": 1,
                "heading_path": [stem, "Table"],
                "columns": header, "row_count": len(data_rows),
            },
        ))

    return chunks


def _sanitize(s: str) -> str:
    return re.sub(r"[^\w]", "_", s.lower())[:50]
