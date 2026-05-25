"""Debug del percorso font-size nel parser PDF."""
import pdfplumber
from pathlib import Path

path = Path("docs/api_reference_v2.pdf")
with pdfplumber.open(str(path)) as pdf:
    page = pdf.pages[0]
    text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
    words_objs = page.extract_words(extra_attrs=["size"]) or []

    sizes = [float(w.get("size", 10)) for w in words_objs if w.get("size")]
    median_size = sorted(sizes)[len(sizes) // 2] if sizes else 0
    heading_threshold = median_size * 1.2
    max_size = max(sizes) if sizes else 0
    size_headings_ok = (max_size > median_size * 1.15)

    print(f"median={median_size} threshold={heading_threshold} max={max_size} size_ok={size_headings_ok}")
    print()

    # Mostra prime 10 parole con size
    print("Prime 10 parole con size:")
    for w in words_objs[:10]:
        print(f"  text={repr(w.get('text'))} size={w.get('size')}")
    print()

    for line in text.splitlines():
        ls = line.strip()
        if not ls:
            continue
        # Nuova logica: word.text in line
        line_words = [w for w in words_objs if w.get("text", "").strip() and w["text"].strip() in ls]
        sizes_found = [float(w.get("size", 0)) for w in line_words]
        is_h = bool(line_words and any(s >= heading_threshold for s in sizes_found))
        matched = [(w["text"], w.get("size")) for w in line_words[:3]]
        print(f"  {'HEADING' if is_h else 'body':7s}: {repr(ls[:50])}")
        print(f"           matched={matched} sizes={sizes_found[:3]}")
