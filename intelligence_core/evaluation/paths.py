"""Risoluzione path adattata al layout reale del repo.

I chunk JSONL del progetto vivono nella CWD (output di ci-parse/ci-embed):
    code   -> chunks.jsonl
    doc    -> doc_chunks.jsonl
    mentor -> mentor_chunks.jsonl

NB: il documento di evoluzione assumeva ~/.intelligence_suite/chunks/, path
che NON esiste in questo progetto. Qui usiamo i file reali in CWD.
"""

from __future__ import annotations

from pathlib import Path

CHUNK_FILES = {
    "code":   "chunks.jsonl",
    "doc":    "doc_chunks.jsonl",
    "mentor": "mentor_chunks.jsonl",
}

COLLECTIONS = {
    "code":   "code_intelligence",
    "doc":    "doc_intelligence",
    "mentor": "mentor_intelligence",
}


def get_chunks_path(domain: str, base_dir: Path | None = None) -> Path:
    base = base_dir or Path.cwd()
    return base / CHUNK_FILES[domain]


def get_collection(domain: str) -> str:
    return COLLECTIONS[domain]
