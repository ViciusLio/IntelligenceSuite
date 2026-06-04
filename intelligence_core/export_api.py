"""Export HTTP route (SOTTO-FASE D).

Mounted by :func:`add_export_routes` on every module server. A single endpoint
turns a client-supplied document (a title + sections — e.g. a chat conversation
or a set of Proposal answers) into a downloadable file.

* ``POST /api/v1/export`` — body ``{format, title, sections}``; returns the
  rendered file as an attachment.

Markdown and HTML are always available (stdlib). PDF needs the optional
``[export]`` extra (``fpdf2``); without it the endpoint returns **503** for
``format=pdf`` while Markdown/HTML keep working. The route sits behind the same
auth middleware as the rest of the app.
"""

from __future__ import annotations

import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from intelligence_core import export

_MEDIA = {
    "markdown": ("text/markdown; charset=utf-8", "md"),
    "html":     ("text/html; charset=utf-8", "html"),
    "pdf":      ("application/pdf", "pdf"),
}


class ExportSection(BaseModel):
    heading: str | None = None
    body:    str = ""
    sources: list[dict] = []


class ExportRequest(BaseModel):
    format:   str = "markdown"          # markdown | html | pdf
    title:    str | None = None
    sections: list[ExportSection] = []


def _safe_filename(title: str | None, module: str) -> str:
    base = (title or f"{module}-export").strip().lower()
    base = re.sub(r"[^a-z0-9._-]+", "-", base).strip("-")
    return base[:60] or f"{module}-export"


def add_export_routes(app: FastAPI, module: str = "code") -> None:
    """Attach ``POST /api/v1/export`` to *app*.

    *module* names the hosting server and seeds the default download filename.
    """

    @app.post("/api/v1/export")
    def export_route(req: ExportRequest):
        fmt = (req.format or "markdown").lower()
        if fmt not in _MEDIA:
            raise HTTPException(status_code=400, detail=f"formato non supportato: {fmt}")

        sections = [s.model_dump() for s in req.sections]
        try:
            if fmt == "markdown":
                content: bytes = export.render_markdown(req.title, sections).encode("utf-8")
            elif fmt == "html":
                content = export.render_html(req.title, sections).encode("utf-8")
            else:  # pdf
                content = export.render_pdf(req.title, sections)
        except export.ExportDependencyError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except export.ExportError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        media, ext = _MEDIA[fmt]
        filename = f"{_safe_filename(req.title, module)}.{ext}"
        return Response(
            content=content,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
