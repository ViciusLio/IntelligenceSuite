"""Debug dettagliato heading detection nel PDF."""
import re
import pdfplumber
from pathlib import Path

with pdfplumber.open("docs/api_reference_v2.pdf") as pdf:
    for page_num, page in enumerate(pdf.pages, 1):
        text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
        words_objs = page.extract_words(extra_attrs=["size"]) or []
        sizes = [float(w.get("size", 10)) for w in words_objs if w.get("size")]
        max_size = max(sizes) if sizes else 0
        median_size = sorted(sizes)[len(sizes)//2] if sizes else 0
        size_headings_ok = max_size > median_size * 1.15 if sizes else False
        print(f"Pagina {page_num}: max={max_size:.1f} median={median_size:.1f} size_ok={size_headings_ok}")
        print()
        for i, line in enumerate(text.splitlines()):
            ls = line.strip()
            if not ls:
                continue
            # Regex test
            m1 = re.match(r"^\d+\.\s+\w", ls)
            m2 = len(ls) < 80 and ls.isupper()
            m3 = re.match(r"^[A-Z][A-Za-z\s\-]{3,60}$", ls) and not any(c in ls for c in ".,;:()[]")
            is_h = bool(m1 or m2 or m3)
            marker = ">>> HEADING" if is_h else "    body"
            print(f"  {marker}: {repr(ls[:60])}  m1={bool(m1)} m2={m2} m3={bool(m3)}")
