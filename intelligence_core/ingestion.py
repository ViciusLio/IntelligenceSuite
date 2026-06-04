"""On-demand ingestion service: parse + embed a path or uploaded files (v0.11.0).

This is the engine behind the optional ingest API/UI. It reuses the *existing*
per-module parsers and the in-store checksum idempotency (only new/changed
chunks are embedded), so it never duplicates work already done by the CLI steps
(``ci-parse``/``di-ingest``/``mi-ingest``/``pi-ingest`` + ``*-embed``).

Design notes
------------
* **Best-effort**: a single unreadable file is logged and skipped, never fatal.
* **Idempotent**: re-ingesting unchanged content embeds nothing (checksum match).
* **Async**: :class:`JobRegistry` tracks background jobs; callers poll by id.
* **Safe paths**: server-side path ingest is confined to ``IS_INGEST_ROOT`` and
  is disabled entirely until that variable is set.

Dependency injection (``persist_dir`` / ``embedder``) exists only so tests can
run fully offline; production callers pass nothing and get the real store/backend.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Modules whose ingest we expose. Maps the public module id → vector domain.
MODULES = ("code", "doc", "mentor", "proposal")
_DOMAIN = {"code": "code", "doc": "doc", "mentor": "mentor", "proposal": "qa"}

_CODE_EXCLUDED = {
    "__pycache__", "build", "dist", "node_modules",
    "venv", ".venv", "env", ".env", ".tox", "site-packages", ".eggs",
}
_QA_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".xlsx"}


# ── errors ────────────────────────────────────────────────────────────────────

class IngestionError(RuntimeError):
    """Base class for ingestion failures surfaced to the caller (→ HTTP 4xx)."""


class IngestionDisabledError(IngestionError):
    """IS_INGEST_ENABLED is false."""


class IngestionRootError(IngestionError):
    """Path ingest misconfigured or target escapes IS_INGEST_ROOT."""


class UnknownModuleError(IngestionError):
    """Requested module is not one of MODULES."""


# ── module dispatch ─────────────────────────────────────────────────────────--

def _check_module(module: str) -> None:
    if module not in MODULES:
        raise UnknownModuleError(
            f"modulo sconosciuto '{module}' (validi: {', '.join(MODULES)})"
        )


def _embed_text(module: str, chunk: dict) -> str:
    """Text fed to the embedder. Proposal matches question-on-question."""
    if module == "proposal":
        return chunk.get("metadata", {}).get("question") or chunk["text"]
    return chunk["text"]


def _get_embedder(module: str):
    from intelligence_core.embedder import get_embedder, get_module_embedder
    return get_module_embedder("pi") if module == "proposal" else get_embedder()


def _chunks_from_file(module: str, file: Path, root: Path) -> list[dict]:
    """Parse a single file into chunks using the module's existing parser."""
    try:
        if module == "code":
            from CodeIntelligence.parsers import get_parser
            parser = get_parser(file)
            return parser.parse_file(file, root) if parser else []
        if module == "doc":
            from DocIntelligence.parsers import get_parser
            parser = get_parser(file)
            return parser.parse_file(file, root) if parser else []
        if module == "mentor":
            from MentorIntelligence.content.ingest_practices import (
                _parse_text_practice,
                _parse_yaml_practice,
            )
            suffix = file.suffix.lower()
            if suffix in {".md", ".txt"}:
                return _parse_text_practice(file, root)
            if suffix in {".yaml", ".yml"}:
                return _parse_yaml_practice(file, root)
            return []
        if module == "proposal":
            if file.suffix.lower() not in _QA_SUFFIXES:
                return []
            from intelligence_core.chunk import make_chunk
            from ProposalIntelligence.qa_parser import parse_qa_pairs
            rel = str(file.relative_to(root)).replace("\\", "/")
            chunks = []
            for q, a in parse_qa_pairs(file):
                import hashlib
                loc = hashlib.sha1(q.strip().lower().encode()).hexdigest()[:16]
                chunks.append(make_chunk(
                    domain="qa", type_="qa_pair", locator=loc,
                    text=f"D: {q}\n\nR: {a}", source=rel, language="mixed",
                    metadata={"question": q, "answer": a, "name": q[:80]},
                ))
            return chunks
    except Exception as e:  # best-effort: one bad file never aborts the run
        logger.warning("ingest: skip %s (%s)", file, e)
    return []


def _iter_files(module: str, root: Path):
    """Yield candidate files under *root*, honouring per-module exclusions."""
    for file in sorted(root.rglob("*")):
        if not file.is_file():
            continue
        parts = file.relative_to(root).parts
        if module == "code":
            if any(
                p.startswith(".") or p in _CODE_EXCLUDED or p.endswith(".egg-info")
                for p in parts
            ):
                continue
        else:
            if any(p.startswith(".") for p in parts):
                continue
        yield file


def _collect_chunks(module: str, files, root: Path) -> list[dict]:
    chunks: list[dict] = []
    for file in files:
        chunks.extend(_chunks_from_file(module, file, root))
    return chunks


# ── embed + store ───────────────────────────────────────────────────────────--

def _embed_and_store(
    module: str,
    chunks: list[dict],
    *,
    prune_orphans: bool,
    persist_dir: str | None = None,
    embedder=None,
) -> dict:
    """Embed only new/changed chunks and upsert into the module's collection."""
    from intelligence_core import paths
    from intelligence_core.config import settings
    from intelligence_core.observability import log_ingestion_event
    from intelligence_core.store import ChromaStore

    t0 = time.perf_counter()
    collection = paths.collection_name(_DOMAIN[module])
    persist = persist_dir or str(paths.chroma_dir())
    store = ChromaStore(collection_name=collection, persist_dir=persist)

    existing = store.get_checksums()
    to_embed = [c for c in chunks if existing.get(c["id"]) != c.get("checksum", "")]

    deleted = 0
    if prune_orphans:
        present = {c["id"] for c in chunks}
        orphans = [i for i in existing if i not in present]
        if orphans:
            store.delete(orphans)
            deleted = len(orphans)

    embedder = embedder or _get_embedder(module)
    batch_size = settings.embed_batch_size
    for i in range(0, len(to_embed), batch_size):
        batch = to_embed[i: i + batch_size]
        embeddings = embedder.embed([_embed_text(module, c) for c in batch])
        for chunk, emb in zip(batch, embeddings):
            chunk["embedding"] = emb

    if to_embed:
        store.add(to_embed)

    duration_ms = (time.perf_counter() - t0) * 1000
    stats = {
        "module":     module,
        "collection": collection,
        "total":      len(chunks),
        "new":        len(to_embed),
        "skipped":    len(chunks) - len(to_embed),
        "deleted":    deleted,
        "indexed":    store.count(),
        "duration_ms": round(duration_ms, 1),
    }
    log_ingestion_event(
        module=_DOMAIN[module],
        project=getattr(settings, "is_project", "default"),
        total=len(chunks), new=len(to_embed), skipped=len(chunks) - len(to_embed),
        duration_ms=duration_ms, backend=settings.embed_backend,
    )
    return stats


# ── synchronous public entry points ─────────────────────────────────────────--

def validate_path(path: str | Path) -> Path:
    """Resolve *path* and assert it lives inside IS_INGEST_ROOT.

    Raises :class:`IngestionDisabledError` / :class:`IngestionRootError`.
    """
    from intelligence_core.config import settings

    if not settings.is_ingest_enabled:
        raise IngestionDisabledError("IS_INGEST_ENABLED è false")
    root_str = settings.is_ingest_root
    if not root_str:
        raise IngestionRootError("IS_INGEST_ROOT non configurato")
    root = Path(root_str).expanduser().resolve()
    target = Path(path).expanduser().resolve()
    if target != root and root not in target.parents:
        raise IngestionRootError(f"path fuori da IS_INGEST_ROOT: {target}")
    if not target.exists():
        raise IngestionRootError(f"path inesistente: {target}")
    return target


def ingest_path(
    module: str,
    path: str | Path,
    *,
    incremental: bool = True,
    persist_dir: str | None = None,
    embedder=None,
) -> dict:
    """Parse+embed every supported file under *path* (must be inside IS_INGEST_ROOT).

    Full-directory scan → orphan IDs (deleted source files) are pruned when
    ``incremental`` is true.
    """
    _check_module(module)
    root = validate_path(path)
    files = [root] if root.is_file() else list(_iter_files(module, root))
    scan_root = root.parent if root.is_file() else root
    chunks = _collect_chunks(module, files, scan_root)
    return _embed_and_store(
        module, chunks, prune_orphans=incremental,
        persist_dir=persist_dir, embedder=embedder,
    )


def ingest_files(
    module: str,
    files: list[Path],
    *,
    root: Path | None = None,
    persist_dir: str | None = None,
    embedder=None,
) -> dict:
    """Parse+embed a set of already-saved (uploaded) files.

    Never prunes orphans: an upload is a *partial* set, so deleting unmatched
    IDs would wipe previously-indexed content.
    """
    _check_module(module)
    files = [Path(f) for f in files]
    if root is None:
        root = Path(files[0]).parent if files else Path(".")
    chunks = _collect_chunks(module, files, root)
    return _embed_and_store(
        module, chunks, prune_orphans=False,
        persist_dir=persist_dir, embedder=embedder,
    )


# ── async jobs ──────────────────────────────────────────────────────────────--

@dataclass
class IngestJob:
    job_id: str
    module: str
    status: str = "queued"            # queued | running | done | error
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    stats: dict | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class JobRegistry:
    """Thread-safe in-memory registry of ingest jobs (mirrors MetricsCollector)."""

    def __init__(self) -> None:
        self._jobs: dict[str, IngestJob] = {}
        self._lock = threading.Lock()

    def create(self, module: str) -> IngestJob:
        job = IngestJob(job_id=uuid.uuid4().hex, module=module)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> IngestJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **changes) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = time.time()


_REGISTRY = JobRegistry()


def get_registry() -> JobRegistry:
    return _REGISTRY


def submit(module: str, work: Callable[[], dict], registry: JobRegistry | None = None) -> str:
    """Run *work* (a no-arg callable returning a stats dict) in a daemon thread.

    Returns the job id immediately; callers poll the registry for completion.
    Any exception is captured into the job's ``error`` field — never raised here.
    """
    _check_module(module)
    registry = registry or _REGISTRY
    job = registry.create(module)

    def _run() -> None:
        registry.update(job.job_id, status="running")
        try:
            stats = work()
            registry.update(job.job_id, status="done", stats=stats)
        except Exception as e:  # best-effort: surface via job status, never crash
            logger.exception("ingest job %s failed", job.job_id)
            registry.update(job.job_id, status="error", error=str(e))

    threading.Thread(target=_run, daemon=True, name=f"ingest-{job.job_id}").start()
    return job.job_id
