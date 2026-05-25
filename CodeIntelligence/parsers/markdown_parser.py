"""Parser Markdown per CodeIntelligence — estrae sezioni e code block."""

from __future__ import annotations
import re
from pathlib import Path

from intelligence_core.chunk import make_chunk


def can_parse(path: Path) -> bool:
    return path.suffix in {".md", ".mdx"}


def parse_file(path: Path, root: Path) -> list[dict]:
    """Ritorna chunk da file Markdown. Fallback a chunk raw."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    rel = str(path.relative_to(root)).replace("\\", "/")
    stem = rel.replace("/", ".").removesuffix(path.suffix)
    chunks = []

    # Split per heading
    heading_re = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    positions = [(m.start(), m.group(1), m.group(2).strip()) for m in heading_re.finditer(source)]

    if not positions:
        preview = source[:2000]
        return [make_chunk(
            domain="code", type_="file", locator=stem,
            text=f"File: {path.name} (in {rel})\n---\n{preview}",
            source=rel, language="markdown",
            metadata={"raw": True},
        )]

    heading_path: list[str] = []

    for i, (pos, level, title) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(source)
        body = source[pos:end].strip()

        depth = len(level)
        heading_path = heading_path[:depth - 1] + [title]

        # Code blocks → chunk separati
        code_blocks = re.findall(r"```(\w*)\n(.*?)```", body, re.DOTALL)
        for lang, code in code_blocks:
            if len(code.strip()) > 20:
                locator = f"{stem}.{_sanitize(title)}.code"
                chunks.append(make_chunk(
                    domain="code", type_="config_block", locator=locator,
                    text=f"CodeBlock ({lang or 'text'}) in {path.name} > {title}\n---\n{code[:1500]}",
                    source=rel, language=lang or "text",
                    metadata={"heading": title, "heading_path": list(heading_path)},
                ))

        section_text = (
            f"Section: {title} (in {rel})\n"
            f"Path: {' > '.join(heading_path)}\n"
            f"---\n{body[:2000]}"
        )
        locator = f"{stem}.{_sanitize(title)}"
        chunks.append(make_chunk(
            domain="code", type_="file", locator=locator,
            text=section_text, source=rel, language="markdown",
            metadata={"heading": title, "heading_path": list(heading_path)},
        ))

    return chunks if chunks else [make_chunk(
        domain="code", type_="file", locator=stem,
        text=f"File: {path.name} (in {rel})\n---\n{source[:2000]}",
        source=rel, language="markdown", metadata={"raw": True},
    )]


def _sanitize(s: str) -> str:
    return re.sub(r"[^\w]", "_", s.lower())[:40]
