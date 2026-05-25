"""Parser TXT — fallback universale: splitta per paragrafi."""

from __future__ import annotations
import re
from pathlib import Path

from intelligence_core.chunk import make_chunk


def can_parse(path: Path) -> bool:
    return path.suffix.lower() in {".txt", ".text", ".log", ".rst"}


def parse_file(path: Path, root: Path) -> list[dict]:
    """Ritorna chunk da testo plain. Ogni paragrafo > 50 chars → un chunk section."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    rel = str(path.relative_to(root)).replace("\\", "/")
    stem = path.stem
    chunks = []

    paragraphs = re.split(r"\n\s*\n", source)
    for i, para in enumerate(paragraphs):
        para = para.strip()
        if len(para) < 50:
            continue
        text = (
            f"Section: {path.name} (paragrafo {i + 1}) (in {rel})\n"
            f"Path: {stem}\n"
            f"---\n{para[:3000]}"
        )
        chunks.append(make_chunk(
            domain="doc", type_="section",
            locator=f"{stem}.p{i + 1}",
            text=text, source=rel, language="text",
            metadata={
                "page_start": 1, "page_end": 1,
                "heading_path": [stem, f"Paragrafo {i + 1}"],
                "word_count": len(para.split()),
            },
        ))

    if not chunks:
        chunks.append(make_chunk(
            domain="doc", type_="section", locator=stem,
            text=f"Section: {path.name} (in {rel})\nPath: {stem}\n---\n{source[:3000]}",
            source=rel, language="text",
            metadata={"page_start": 1, "page_end": 1, "heading_path": [stem]},
        ))

    return chunks
