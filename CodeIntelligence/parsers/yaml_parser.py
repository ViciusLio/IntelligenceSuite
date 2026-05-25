"""Parser YAML — estrae config block come chunk leggibili."""

from __future__ import annotations
from pathlib import Path

from intelligence_core.chunk import make_chunk


def can_parse(path: Path) -> bool:
    return path.suffix in {".yaml", ".yml"}


def parse_file(path: Path, root: Path) -> list[dict]:
    """Ritorna chunk da file YAML. Fallback a chunk raw."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    rel = str(path.relative_to(root)).replace("\\", "/")
    stem = rel.replace("/", ".").removesuffix(path.suffix)

    # TODO: implement structured YAML parsing (top-level keys → chunk per sezione)
    # Per ora: un chunk per file con il contenuto raw
    preview = source[:2000]
    text = f"Config: {path.name} (in {rel})\n---\n{preview}"
    if len(source) > 2000:
        text += f"\n... ({len(source) - 2000} chars omessi)"

    return [make_chunk(
        domain="code", type_="config_block", locator=stem,
        text=text, source=rel, language="yaml",
        metadata={"raw": True, "size_bytes": len(source)},
    )]
