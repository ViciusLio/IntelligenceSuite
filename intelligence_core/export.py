"""Export renderers (SOTTO-FASE D).

Render a small structured document — a title plus a list of sections, each with
an optional heading, a body, and optional source chips — to **Markdown**, a
standalone **HTML** page, or a **PDF**.

Markdown and HTML are stdlib-only and always available. PDF needs ``fpdf2``,
shipped via the optional ``[export]`` extra; when absent, :func:`render_pdf`
raises :class:`ExportDependencyError` (the HTTP layer maps it to 503) so the
other two formats keep working.

A *section* is a plain dict::

    {"heading": str | None, "body": str, "sources": [{"source": str, ...}, ...]}
"""

from __future__ import annotations

from html import escape

# fpdf2 is optional — only needed for PDF output (the ``[export]`` extra).
try:
    import fpdf  # noqa: F401
    _HAS_FPDF = True
except Exception:
    _HAS_FPDF = False


class ExportError(RuntimeError):
    """Base class for export failures."""


class ExportDependencyError(ExportError):
    """Raised when PDF output is requested but ``fpdf2`` is not installed."""


# ── helpers ──────────────────────────────────────────────────────────────────

def _source_names(sources) -> list[str]:
    names = []
    for s in sources or []:
        name = s.get("source") or s.get("id") or s.get("type")
        if name:
            names.append(str(name))
    return names


# Map a few common non-latin-1 characters so the core-font PDF doesn't choke.
_PDF_SUBST = {
    "—": "-", "–": "-",          # em / en dash
    "‘": "'", "’": "'",          # curly single quotes
    "“": '"', "”": '"',          # curly double quotes
    "…": "...", "•": "-",        # ellipsis, bullet
    " ": " ",                          # nbsp
}


def _pdf_safe(text: str) -> str:
    """Make *text* renderable by fpdf2's latin-1 core fonts (best-effort)."""
    for bad, good in _PDF_SUBST.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", "replace").decode("latin-1")


# ── Markdown ─────────────────────────────────────────────────────────────────

def render_markdown(title: str | None, sections: list[dict]) -> str:
    lines: list[str] = []
    if title:
        lines.append(f"# {title}")
        lines.append("")
    for sec in sections:
        heading = (sec.get("heading") or "").strip()
        if heading:
            lines.append(f"## {heading}")
            lines.append("")
        body = (sec.get("body") or "").strip()
        if body:
            lines.append(body)
            lines.append("")
        names = _source_names(sec.get("sources"))
        if names:
            lines.append("_Fonti: " + ", ".join(names) + "_")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ── HTML ─────────────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          max-width: 820px; margin: 2rem auto; padding: 0 1.25rem; color: #1f2937;
          line-height: 1.6; }}
  h1 {{ font-size: 1.6rem; border-bottom: 2px solid #e5e7eb; padding-bottom: .4rem; }}
  h2 {{ font-size: 1.1rem; color: #4f46e5; margin-top: 1.6rem; }}
  .body {{ white-space: pre-wrap; }}
  .sources {{ margin-top: .5rem; font-size: .8rem; color: #6b7280; }}
  .chip {{ display: inline-block; background: #f1f5f9; color: #475569;
           border-radius: 999px; padding: 1px 8px; margin: 2px 4px 2px 0; }}
</style>
</head>
<body>
{heading}
{body}
</body>
</html>
"""


def render_html(title: str | None, sections: list[dict]) -> str:
    heading_html = f"<h1>{escape(title)}</h1>" if title else ""
    parts: list[str] = []
    for sec in sections:
        heading = (sec.get("heading") or "").strip()
        if heading:
            parts.append(f"<h2>{escape(heading)}</h2>")
        body = (sec.get("body") or "").strip()
        if body:
            parts.append(f'<div class="body">{escape(body)}</div>')
        names = _source_names(sec.get("sources"))
        if names:
            chips = "".join(f'<span class="chip">{escape(n)}</span>' for n in names)
            parts.append(f'<div class="sources">Fonti: {chips}</div>')
    return _HTML_TEMPLATE.format(
        title=escape(title or "Export"),
        heading=heading_html,
        body="\n".join(parts),
    )


# ── PDF (optional — needs the ``[export]`` extra) ────────────────────────────--

def render_pdf(title: str | None, sections: list[dict]) -> bytes:
    if not _HAS_FPDF:
        raise ExportDependencyError(
            "PDF export richiede il pacchetto 'fpdf2'. "
            "Installa intelligence-suite[export] per abilitarlo."
        )
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    # Each multi_cell must drop the cursor back to the left margin on a new line;
    # fpdf2's default (new_x=RIGHT) otherwise leaves ~0 width for the next call.
    nl = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    if title:
        pdf.set_font("Helvetica", "B", 16)
        pdf.multi_cell(0, 9, _pdf_safe(title), **nl)
        pdf.ln(2)

    for sec in sections:
        heading = (sec.get("heading") or "").strip()
        if heading:
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(0, 6, _pdf_safe(heading), **nl)
        body = (sec.get("body") or "").strip()
        if body:
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 5, _pdf_safe(body), **nl)
        names = _source_names(sec.get("sources"))
        if names:
            pdf.set_font("Helvetica", "I", 9)
            pdf.multi_cell(0, 5, _pdf_safe("Fonti: " + ", ".join(names)), **nl)
        pdf.ln(3)

    out = pdf.output()        # fpdf2 2.x → bytearray
    return bytes(out)
