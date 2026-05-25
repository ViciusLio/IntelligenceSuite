"""Debug del parser PDF."""
from pathlib import Path
from DocIntelligence.parsers.pdf_parser import parse_file

chunks = parse_file(Path("docs/api_reference_v2.pdf"), Path("docs"))
print(f"Totale chunk: {len(chunks)}")
for c in chunks:
    print(f"  type={c['type']:12s}  id={c['id']}")
    print(f"  text[:100]={repr(c['text'][:100])}")
    print()

# Debug pdfplumber diretto
import pdfplumber
with pdfplumber.open("docs/api_reference_v2.pdf") as pdf:
    print(f"Pagine: {len(pdf.pages)}")
    for i, page in enumerate(pdf.pages, 1):
        text = page.extract_text() or ""
        words = page.extract_words(extra_attrs=["size"]) or []
        sizes = [w.get("size") for w in words[:5]]
        print(f"  Pagina {i}: {len(text)} chars, {len(words)} words, sizes campione={sizes}")
        print(f"  Testo[:200]={repr(text[:200])}")
