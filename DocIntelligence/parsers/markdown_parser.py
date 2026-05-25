"""Parser Markdown per DocIntelligence — sezioni e code_example chunk."""

from __future__ import annotations
import re
from pathlib import Path

from intelligence_core.chunk import make_chunk


def can_parse(path: Path) -> bool:
    return path.suffix in {".md", ".mdx", ".markdown"}


def parse_file(path: Path, root: Path) -> list[dict]:
    """Ritorna chunk da Markdown. Fallback a chunk raw."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    rel = str(path.relative_to(root)).replace("\\", "/")
    stem = path.stem
    chunks = []

    heading_re = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    positions = [(m.start(), len(m.group(1)), m.group(2).strip())
                 for m in heading_re.finditer(source)]

    if not positions:
        text = f"Section: {path.name} (in {rel})\nPath: {stem}\n---\n{source[:3000]}"
        return [make_chunk(
            domain="doc", type_="section", locator=stem,
            text=text, source=rel, language="markdown",
            metadata={"page_start": 1, "page_end": 1, "heading_path": [stem], "word_count": len(source.split())},
        )]

    heading_path: list[str] = []

    for i, (pos, depth, title) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(source)
        body = source[pos:end].strip()
        heading_path = heading_path[:depth - 1] + [title]

        # Code block → chunk code_example
        code_blocks = re.findall(r"```(\w*)\n(.*?)```", body, re.DOTALL)
        for lang, code in code_blocks:
            if len(code.strip()) > 20:
                chunks.append(make_chunk(
                    domain="doc", type_="code_example",
                    locator=f"{stem}.{_sanitize(title)}.code",
                    text=(
                        f"CodeExample ({lang or 'text'}) in {path.name} > {title}\n"
                        f"---\n{code[:2000]}"
                    ),
                    source=rel, language=lang or "text",
                    metadata={"page_start": 1, "page_end": 1,
                              "heading_path": list(heading_path)},
                ))

        text = (
            f"Section: {title} (in {path.name})\n"
            f"Path: {' > '.join(heading_path)}\n"
            f"---\n{body[:3000]}"
        )
        chunks.append(make_chunk(
            domain="doc", type_="section",
            locator=f"{stem}.{_sanitize(title)}",
            text=text[:7500], source=rel, language="markdown",
            metadata={
                "page_start": 1, "page_end": 1,
                "heading_path": list(heading_path),
                "word_count": len(body.split()),
            },
        ))

    return chunks if chunks else [make_chunk(
        domain="doc", type_="section", locator=stem,
        text=f"Section: {path.name} (in {rel})\nPath: {stem}\n---\n{source[:3000]}",
        source=rel, language="markdown",
        metadata={"page_start": 1, "page_end": 1, "heading_path": [stem]},
    )]


def _sanitize(s: str) -> str:
    return re.sub(r"[^\w]", "_", s.lower())[:50]
