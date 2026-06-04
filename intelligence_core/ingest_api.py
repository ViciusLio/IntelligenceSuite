"""Optional ingest HTTP routes (v0.12.0).

Mounted by :func:`add_ingest_routes` **only when** ``IS_INGEST_ENABLED`` is true.
When disabled (the default) no routes are added, so the endpoints return 404 and
behavior is identical to v0.11.x. All routes sit behind the existing
``BearerAuthMiddleware`` (auth is wired one layer up in ``create_app``).

Endpoints
---------
* ``POST /api/v1/ingest/path``          — index a server-side path (inside
  ``IS_INGEST_ROOT``); returns a ``job_id`` and runs the work asynchronously.
* ``POST /api/v1/ingest/upload``        — index uploaded files; needs the
  ``[ingest]`` extra (``python-multipart``). Absent → route not mounted (404).
* ``GET  /api/v1/ingest/status/{job_id}`` — poll a job's status/stats.

The heavy parse+embed always runs in a background thread (see
``intelligence_core.ingestion.submit``); the HTTP call returns immediately.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from intelligence_core import ingestion

logger = logging.getLogger(__name__)

# python-multipart is required by Starlette to parse multipart/form-data uploads.
# It ships with the optional ``[ingest]`` extra; without it the upload route is
# simply not mounted (path + status still work).
try:
    import multipart  # noqa: F401
    _HAS_MULTIPART = True
except Exception:
    _HAS_MULTIPART = False


class IngestPathRequest(BaseModel):
    path: str
    module: str | None = None     # defaults to the hosting server's module
    incremental: bool = True


def _resolve_module(requested: str | None, default: str) -> str:
    module = requested or default
    ingestion._check_module(module)   # raises UnknownModuleError
    return module


def add_ingest_routes(app: FastAPI, module: str = "code") -> None:
    """Attach the ingest routes to *app* when IS_INGEST_ENABLED is true.

    *module* is the hosting server's domain and the default target for ingest
    requests that don't specify one.
    """
    from intelligence_core.config import settings

    if not settings.is_ingest_enabled:
        return

    default_module = module

    # ── server-side path ingest ────────────────────────────────────────────────
    @app.post("/api/v1/ingest/path")
    def ingest_path_route(req: IngestPathRequest):
        try:
            mod = _resolve_module(req.module, default_module)
            target = ingestion.validate_path(req.path)
        except ingestion.IngestionDisabledError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except ingestion.IngestionError as exc:        # unknown module / bad path
            raise HTTPException(status_code=400, detail=str(exc))

        def work() -> dict:
            return ingestion.ingest_path(mod, target, incremental=req.incremental)

        job_id = ingestion.submit(mod, work)
        return {"job_id": job_id, "status": "queued", "module": mod, "path": str(target)}

    # ── job status ─────────────────────────────────────────────────────────────
    @app.get("/api/v1/ingest/status/{job_id}")
    def ingest_status_route(job_id: str):
        job = ingestion.get_registry().get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"job sconosciuto: {job_id}")
        return job.to_dict()

    # ── uploaded-files ingest (needs python-multipart → [ingest] extra) ─────────
    if not _HAS_MULTIPART:
        logger.warning(
            "ingest: upload route disabilitata (manca python-multipart). "
            "Installa intelligence-suite[ingest] per abilitarla."
        )
        return

    @app.post("/api/v1/ingest/upload")
    async def ingest_upload_route(
        files: list[UploadFile] = File(...),
        module: str | None = Form(None),
    ):
        try:
            mod = _resolve_module(module, default_module)
        except ingestion.IngestionError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not files:
            raise HTTPException(status_code=400, detail="nessun file caricato")

        max_bytes = settings.is_ingest_max_mb * 1024 * 1024
        tmpdir = tempfile.mkdtemp(prefix="is_ingest_")
        tmp_root = Path(tmpdir)
        saved: list[Path] = []
        try:
            for upload in files:
                name = Path(upload.filename or "upload").name  # strip any path
                data = await upload.read()
                if len(data) > max_bytes:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"{name} supera IS_INGEST_MAX_MB ({settings.is_ingest_max_mb} MB)",
                    )
                dest = tmp_root / name
                dest.write_bytes(data)
                saved.append(dest)
        except HTTPException:
            raise
        except Exception as exc:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=f"upload fallito: {exc}")

        def work() -> dict:
            try:
                return ingestion.ingest_files(mod, saved, root=tmp_root)
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

        job_id = ingestion.submit(mod, work)
        return {"job_id": job_id, "status": "queued", "module": mod, "files": len(saved)}
