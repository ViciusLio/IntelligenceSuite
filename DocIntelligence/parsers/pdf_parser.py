"""Parser PDF a 3 livelli: pdfplumber → OCR → raw. Best-effort, mai crasha."""

from __future__ import annotations
import re
from pathlib import Path

from intelligence_core.chunk import make_chunk

try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False


def can_parse(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"


def parse_file(path: Path, root: Path) -> list[dict]:
    """Ritorna chunk da PDF. Sempre ritorna almeno 1 chunk."""
    rel = str(path.relative_to(root)).replace("\\", "/")
    stem = path.stem

    if HAS_PDF:
        try:
            return _parse_with_pdfplumber(path, rel, stem)
        except Exception:
            pass

    if HAS_OCR:
        try:
            return _parse_with_ocr(path, rel, stem)
        except Exception:
            pass

    return _fallback_chunk(path, rel, stem)


# ── Livello 1: pdfplumber ────────────────────────────────────────────────────

def _parse_with_pdfplumber(path: Path, rel: str, stem: str) -> list[dict]:
    chunks = []
    with pdfplumber.open(str(path)) as pdf:
        current_heading: list[str] = [stem]
        current_body: list[str] = []
        current_page_start = 1
        current_page_end = 1

        def flush_section():
            if not current_body:
                return
            body_text = "\n".join(current_body).strip()
            if len(body_text) < 30:
                return
            heading = current_heading[-1] if current_heading else stem
            text = (
                f"Section: {heading} (in {path.name})\n"
                f"Path: {' > '.join(current_heading)}\n"
                f"---\n{body_text}"
            )
            locator = f"{stem}.{_sanitize(heading)}"
            words = body_text.split()
            if len(words) <= 1500:
                chunks.append(make_chunk(
                    domain="doc", type_="section", locator=locator,
                    text=text[:7500], source=rel, language="pdf",
                    metadata={
                        "page_start": current_page_start,
                        "page_end":   current_page_end,
                        "heading_path": list(current_heading),
                        "word_count": len(words),
                    },
                ))
            else:
                # Spezza in chunk sovrapposti
                overlap = 100
                chunk_size = 1500
                for i in range(0, len(words), chunk_size - overlap):
                    part_words = words[i: i + chunk_size]
                    part_text = (
                        f"Section: {heading} (parte {i // (chunk_size - overlap) + 1}) "
                        f"(in {path.name})\n"
                        f"Path: {' > '.join(current_heading)}\n"
                        f"---\n{' '.join(part_words)}"
                    )
                    chunks.append(make_chunk(
                        domain="doc", type_="section",
                        locator=f"{locator}_p{i // (chunk_size - overlap) + 1}",
                        text=part_text[:7500], source=rel, language="pdf",
                        metadata={
                            "page_start": current_page_start,
                            "page_end":   current_page_end,
                            "heading_path": list(current_heading),
                            "word_count": len(part_words),
                            "split": True,
                        },
                    ))

        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            if len(text.strip()) < 50 and HAS_OCR:
                # Fallback OCR per pagina scarsa
                try:
                    img = page.to_image(resolution=200).original
                    text = pytesseract.image_to_string(img)
                except Exception:
                    pass

            # Analisi font-size per rilevare heading
            words_objs = []
            try:
                words_objs = page.extract_words(extra_attrs=["size"]) or []
            except Exception:
                pass

            # Cerca di rilevare heading via font size, poi via regex
            size_headings_ok = False
            heading_threshold = 0.0
            # Mappa prefix-riga → font-size medio, costruita raggruppando le
            # parole per coordinata y (approccio robusto, evita false match
            # per parole comuni come "e"/"in" che compaiono a più dimensioni).
            _line_size_map: dict[str, float] = {}
            if words_objs:
                from collections import defaultdict as _dd
                sizes = [float(w.get("size", 0)) for w in words_objs if w.get("size")]
                if sizes:
                    median_size = sorted(sizes)[len(sizes) // 2]
                    heading_threshold = median_size * 1.2
                    max_size = max(sizes)
                    size_headings_ok = (max_size > median_size * 1.15)
                # Raggruppa parole per riga (coordinata y arrotondata)
                _by_top: dict[float, list] = _dd(list)
                for _w in words_objs:
                    if _w.get("text", "").strip():
                        _by_top[round(float(_w.get("top", 0)), 0)].append(_w)
                for _wlist in _by_top.values():
                    _reconstructed = " ".join(_w["text"] for _w in _wlist).strip()
                    if _reconstructed:
                        _avg_sz = (
                            sum(float(_w.get("size", 0)) for _w in _wlist)
                            / len(_wlist)
                        )
                        _line_size_map[_reconstructed[:40]] = _avg_sz

            import re as _re

            for line in text.splitlines():
                line_stripped = line.strip()
                if not line_stripped:
                    continue

                if size_headings_ok:
                    # Usa la dimensione media della riga ricostruita da y-coord
                    _key = line_stripped[:40]
                    _font = _line_size_map.get(_key, 0.0)
                    is_heading = (
                        bool(_font >= heading_threshold)
                        and len(line_stripped) < 120
                    )
                else:
                    # Heuristica testuale: linee numerate "N. Titolo" o breve titolo
                    is_heading = bool(
                        _re.match(r"^\d+\.\s+\w", line_stripped)
                        or (len(line_stripped) < 80 and line_stripped.isupper())
                        or _re.match(r"^[A-Z][A-Za-z\s\-]{3,60}$", line_stripped)
                        and not any(c in line_stripped for c in ".,;:()[]")
                    )

                if is_heading:
                    flush_section()
                    current_body = []
                    current_heading = current_heading[:1] + [line_stripped]
                    current_page_start = page_num
                    current_page_end = page_num
                else:
                    current_body.append(line_stripped)
                    current_page_end = page_num

        flush_section()

    # Se non abbiamo estratto sezioni strutturate (< 3), tenta fallback per pagina
    section_chunks = [c for c in chunks if c.get("type") == "section"]
    if len(section_chunks) < 3:
        fallback = _fallback_per_page(path, rel, stem)
        if len(fallback) > len(chunks):
            return fallback

    if not chunks:
        chunks = _fallback_per_page(path, rel, stem)

    return chunks


def _fallback_per_page(path: Path, rel: str, stem: str) -> list[dict]:
    chunks = []
    with pdfplumber.open(str(path)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if len(text) < 30:
                continue
            chunks.append(make_chunk(
                domain="doc", type_="section",
                locator=f"{stem}.page_{page_num}",
                text=f"Section: Pagina {page_num} (in {path.name})\nPath: {stem}\n---\n{text[:3000]}",
                source=rel, language="pdf",
                metadata={"page_start": page_num, "page_end": page_num,
                          "heading_path": [stem, f"Pagina {page_num}"], "word_count": len(text.split())},
            ))
    return chunks if chunks else _fallback_chunk(path, rel, stem)


# ── Livello 2: OCR ──────────────────────────────────────────────────────────

def _parse_with_ocr(path: Path, rel: str, stem: str) -> list[dict]:
    import pypdf
    chunks = []
    with open(str(path), "rb") as f:
        reader = pypdf.PdfReader(f)
        for page_num, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if len(text) < 50:
                continue
            chunks.append(make_chunk(
                domain="doc", type_="section",
                locator=f"{stem}.page_{page_num}",
                text=f"Section: Pagina {page_num} (in {path.name})\nPath: {stem}\n---\n{text[:3000]}",
                source=rel, language="pdf",
                metadata={"page_start": page_num, "page_end": page_num,
                          "heading_path": [stem, f"Pagina {page_num}"], "word_count": len(text.split())},
            ))
    return chunks if chunks else _fallback_chunk(path, rel, stem)


# ── Livello 3: fallback ──────────────────────────────────────────────────────

def _fallback_chunk(path: Path, rel: str, stem: str) -> list[dict]:
    try:
        data = path.read_bytes()
        text_parts = re.findall(rb"[\x20-\x7E\n\r\t]{4,}", data)
        raw = b" ".join(text_parts).decode("ascii", errors="replace")[:2000]
    except Exception:
        raw = f"[Contenuto non estraibile da {path.name}]"

    return [make_chunk(
        domain="doc", type_="section", locator=f"{stem}.raw",
        text=f"Section: {path.name} (raw fallback)\nPath: {stem}\n---\n{raw}",
        source=rel, language="pdf",
        metadata={"page_start": 1, "page_end": 1, "heading_path": [stem], "raw": True},
    )]


def _sanitize(s: str) -> str:
    return re.sub(r"[^\w]", "_", s.lower())[:50]
