"""Entry point: scansiona una repo e produce chunk JSONL."""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from CodeIntelligence.parsers import get_parser
from intelligence_core.chunk import chunk_to_jsonl, validate_chunk


_EXCLUDED_DIRS = {
    "__pycache__", "build", "dist", "node_modules",
    "venv", ".venv", "env", ".env", ".tox",
    "site-packages", ".eggs",
}


def parse_repo(repo_path: Path, output: Path = None) -> list[dict]:
    chunks = []
    skipped = 0
    for file in sorted(repo_path.rglob("*")):
        if not file.is_file():
            continue
        parts = set(file.relative_to(repo_path).parts)
        if any(
            p.startswith(".") or p in _EXCLUDED_DIRS or p.endswith(".egg-info")
            for p in parts
        ):
            continue
        parser = get_parser(file)
        if parser is None:
            skipped += 1
            continue
        try:
            file_chunks = parser.parse_file(file, repo_path)
            chunks.extend(file_chunks)
        except Exception as e:
            print(f"  WARN: {file}: {e}", file=sys.stderr)

    print(f"Parsed: {len(chunks)} chunk, {skipped} file senza parser")

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(chunk_to_jsonl(c) + "\n")
        print(f"Output: {output}")

    return chunks


def main():
    parser = argparse.ArgumentParser(description="Parsa una repo in chunk JSONL")
    parser.add_argument("repo", nargs="?", default=".", help="Path alla repo (default: .)")
    parser.add_argument("-o", "--output", default="chunks.jsonl")
    args = parser.parse_args()
    parse_repo(Path(args.repo), Path(args.output))


if __name__ == "__main__":
    main()
