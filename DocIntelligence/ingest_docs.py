"""Entry point: scansiona una directory di documenti e produce chunk JSONL."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from DocIntelligence.parsers import get_parser
from intelligence_core.chunk import chunk_to_jsonl, chunk_from_jsonl


def _file_hash(path: Path) -> str:
    """SHA-256 of file content (stream-read, safe for large files)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def ingest_docs(
    docs_path: Path,
    output: Path = None,
    incremental: bool = False,
) -> list[dict]:
    """Scansiona la directory documenti e produce chunk JSONL.

    Args:
        docs_path:   Root della directory documenti da analizzare.
        output:      File JSONL di output (default: doc_chunks.jsonl nella CWD).
        incremental: Se True, salta i file non modificati comparando SHA-256.
                     Il file di stato viene salvato come <output>.state.json.
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
                print(f"  WARN: state file non leggibile ({e}) — eseguo full ingest")

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
                print(f"  WARN: JSONL precedente non leggibile ({e}) — eseguo full ingest")

    # ── Scan files ───────────────────────────────────────────────────────────
    chunks: list[dict] = []
    new_hashes: dict[str, str] = {}
    skipped = 0
    files_unchanged = 0
    files_reingested = 0

    for file in sorted(docs_path.rglob("*")):
        if not file.is_file():
            continue
        if any(part.startswith(".") for part in file.parts):
            continue
        parser = get_parser(file)
        if parser is None:
            skipped += 1
            continue

        rel = str(file.relative_to(docs_path)).replace("\\", "/")

        if incremental:
            file_h = _file_hash(file)
            new_hashes[rel] = file_h
            if prev_hashes.get(rel) == file_h and rel in prev_chunks_by_source:
                chunks.extend(prev_chunks_by_source[rel])
                files_unchanged += 1
                continue

        file_chunks = parser.parse_file(file, docs_path)
        chunks.extend(file_chunks)
        files_reingested += 1
        if not incremental:
            print(f"  {file.name}: {len(file_chunks)} chunk")

    if incremental:
        print(
            f"  File invariati: {files_unchanged} | "
            f"File ri-ingestati: {files_reingested} | "
            f"Senza parser: {skipped}"
        )
    print(f"Totale: {len(chunks)} chunk, {skipped} file senza parser")

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
    parser = argparse.ArgumentParser(description="Ingesta documenti in chunk JSONL")
    parser.add_argument("docs", nargs="?", default="./docs")
    parser.add_argument("-o", "--output", default="doc_chunks.jsonl")
    parser.add_argument(
        "--incremental", action="store_true",
        help=(
            "Salta i file non modificati confrontando l'hash SHA-256 del contenuto. "
            "Il file di stato viene salvato accanto all'output come <output>.state.json."
        ),
    )
    args = parser.parse_args()
    ingest_docs(Path(args.docs), Path(args.output), incremental=args.incremental)


if __name__ == "__main__":
    main()
