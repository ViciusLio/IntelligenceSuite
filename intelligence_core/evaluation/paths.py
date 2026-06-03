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

# Domini reali (escluso lo pseudo-dominio "all" usato per l'eval integrato).
BASE_DOMAINS = ("code", "doc", "mentor")


def get_chunks_path(domain: str, base_dir: Path | None = None) -> Path:
    base = base_dir or Path.cwd()
    return base / CHUNK_FILES[domain]


def get_all_chunk_paths(base_dir: Path | None = None) -> list[Path]:
    """Path dei chunk di tutti i domini base che esistono su disco (eval 'all')."""
    return [
        p for p in (get_chunks_path(d, base_dir) for d in BASE_DOMAINS) if p.exists()
    ]


def get_collection(domain: str) -> str:
    from intelligence_core import paths
    return paths.collection_name(domain)


def get_all_collections() -> list[str]:
    """Nomi di tutte le collection (con prefisso progetto se IS_PROJECT != 'default')."""
    from intelligence_core import paths
    return [paths.collection_name(d) for d in BASE_DOMAINS]
