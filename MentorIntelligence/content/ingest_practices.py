"""Ingesta prassi aziendali come chunk domain=mentor nel vector store."""

from __future__ import annotations
import argparse
import re
from pathlib import Path

from intelligence_core.chunk import make_chunk, chunk_to_jsonl

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def ingest_practices(practices_dir: Path, output: Path = None) -> list[dict]:
    """Scansiona la directory e ingesta i file come chunk mentor."""
    chunks = []
    for file in sorted(practices_dir.rglob("*")):
        if not file.is_file():
            continue
        if file.suffix in {".md", ".txt"}:
            chunks.extend(_parse_text_practice(file, practices_dir))
        elif file.suffix in {".yaml", ".yml"} and HAS_YAML:
            chunks.extend(_parse_yaml_practice(file, practices_dir))

    print(f"Prassi ingested: {len(chunks)} chunk da {practices_dir}")

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(chunk_to_jsonl(c) + "\n")
        print(f"Output: {output}")

    return chunks


def _parse_text_practice(file: Path, root: Path) -> list[dict]:
    text = file.read_text(encoding="utf-8", errors="replace").strip()
    rel = str(file.relative_to(root)).replace("\\", "/")
    stem = file.stem
    if len(text) < 30:
        return []

    heading = stem.replace("_", " ").replace("-", " ").title()
    chunk_text = (
        f"Practice: {heading} (in {file.name})\n"
        f"Categoria: generale\n"
        f"---\n{text[:3000]}"
    )
    return [make_chunk(
        domain="mentor", type_="practice",
        locator=f"practice.{_sanitize(stem)}",
        text=chunk_text, source=rel, language="markdown",
        metadata={"category": "generale", "priority": "normale", "audience": ["all"]},
    )]


def _parse_yaml_practice(file: Path, root: Path) -> list[dict]:
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
    except Exception:
        return _parse_text_practice(file, root)

    rel = str(file.relative_to(root)).replace("\\", "/")
    title = data.get("title", file.stem)
    practice_type = data.get("type", "practice")
    category = data.get("category", "generale")
    priority = data.get("priority", "normale")
    audience = data.get("audience", ["all"])
    content = data.get("content", "")

    if not content or len(str(content)) < 30:
        return []

    chunk_text = (
        f"Practice: {title} (in {file.name})\n"
        f"Categoria: {category} | Priorita: {priority}\n"
        f"---\n{str(content)[:3000]}"
    )
    return [make_chunk(
        domain="mentor", type_=practice_type,
        locator=f"practice.{_sanitize(title)}",
        text=chunk_text, source=rel, language="yaml",
        metadata={"category": category, "priority": priority, "audience": audience},
    )]


def _sanitize(s: str) -> str:
    return re.sub(r"[^\w]", "_", s.lower())[:50]


def main():
    parser = argparse.ArgumentParser(description="Ingesta prassi aziendali come chunk mentor")
    parser.add_argument("practices", nargs="?", default="./practices")
    parser.add_argument("-o", "--output", default="mentor_chunks.jsonl")
    args = parser.parse_args()
    ingest_practices(Path(args.practices), Path(args.output))


if __name__ == "__main__":
    main()
