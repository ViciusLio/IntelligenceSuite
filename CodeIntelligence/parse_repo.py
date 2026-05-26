"""Entry point: scansiona una repo e produce chunk JSONL."""

from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

from CodeIntelligence.parsers import get_parser
from intelligence_core.chunk import chunk_to_jsonl, chunk_from_jsonl, validate_chunk


_EXCLUDED_DIRS = {
    "__pycache__", "build", "dist", "node_modules",
    "venv", ".venv", "env", ".env", ".tox",
    "site-packages", ".eggs",
}


def _file_hash(path: Path) -> str:
    """SHA-256 of file content (stream-read, safe for large files)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def parse_repo(
    repo_path: Path,
    output: Path = None,
    incremental: bool = False,
) -> list[dict]:
    """Scansiona la repo e produce chunk JSONL.

    Args:
        repo_path:   Root della repository da analizzare.
        output:      File JSONL di output (default: chunks.jsonl nella CWD).
        incremental: Se True, salta i file non modificati comparando SHA-256.
                     Richiede un file `<output>.state.json` da una run precedente.
                     Alla fine della run il file di stato viene aggiornato.
    """
    # ── Load previous state (incremental mode) ──────────────────────────────
    state_file = output.with_suffix(".state.json") if output else None
    prev_hashes: dict[str, str] = {}
    prev_chunks_by_source: dict[str, list[dict]] = {}

    if incremental:
        if state_file and state_file.exists():
            try:
                prev_hashes = json.loads(state_file.read_text(encoding="utf-8"))
                print(f"  Incremental: stato precedente caricato ({len(prev_hashes)} file tracciati)")
            except Exception as e:
                print(f"  WARN: state file non leggibile ({e}) — eseguo full parse")

        if output and output.exists():
            try:
                with output.open(encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        c = json.loads(line)
                        src = c.get("source", "")
                        prev_chunks_by_source.setdefault(src, []).append(c)
            except Exception as e:
                print(f"  WARN: JSONL precedente non leggibile ({e}) — eseguo full parse")

    # ── Scan files ───────────────────────────────────────────────────────────
    chunks: list[dict] = []
    new_hashes: dict[str, str] = {}
    skipped = 0
    files_unchanged = 0
    files_reparsed = 0

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

        # Normalise to forward slashes (matches parser.parse_file convention)
        rel = str(file.relative_to(repo_path)).replace("\\", "/")

        if incremental:
            file_h = _file_hash(file)
            new_hashes[rel] = file_h
            if prev_hashes.get(rel) == file_h and rel in prev_chunks_by_source:
                chunks.extend(prev_chunks_by_source[rel])
                files_unchanged += 1
                continue

        try:
            file_chunks = parser.parse_file(file, repo_path)
            chunks.extend(file_chunks)
            files_reparsed += 1
        except Exception as e:
            print(f"  WARN: {file}: {e}", file=sys.stderr)

    if incremental:
        print(
            f"  File invariati: {files_unchanged} | "
            f"File ri-parsati: {files_reparsed} | "
            f"Senza parser: {skipped}"
        )
    print(f"Parsed: {len(chunks)} chunk totali, {skipped} file senza parser")

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(chunk_to_jsonl(c) + "\n")
        print(f"Output: {output}")

        if incremental and state_file:
            state_file.write_text(
                json.dumps(new_hashes, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"State:  {state_file}")

    return chunks


def main():
    parser = argparse.ArgumentParser(description="Parsa una repo in chunk JSONL")
    parser.add_argument("repo", nargs="?", default=".", help="Path alla repo (default: .)")
    parser.add_argument("-o", "--output", default="chunks.jsonl")
    parser.add_argument(
        "--incremental", action="store_true",
        help=(
            "Salta i file non modificati confrontando l'hash SHA-256 del contenuto. "
            "Il file di stato viene salvato accanto all'output come <output>.state.json."
        ),
    )
    args = parser.parse_args()
    parse_repo(Path(args.repo), Path(args.output), incremental=args.incremental)


if __name__ == "__main__":
    main()
