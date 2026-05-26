"""Ingest company best-practice documents as mentor chunks into ChromaDB."""

from __future__ import annotations
import argparse
import re
from pathlib import Path

from intelligence_core.chunk import make_chunk, chunk_to_jsonl

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

COLLECTION_NAME = "mentor_intelligence"


def ingest_practices(
    practices_dir: Path,
    output: Path = None,
    collection_name: str = COLLECTION_NAME,
) -> list[dict]:
    """
    Full pipeline step:
      1. Parse MD / TXT / YAML practice files into mentor chunks
      2. Compute embeddings
      3. Write JSONL (optional)
      4. Upsert into ChromaDB — collection ready for mi-serve

    Args:
        practices_dir:    Directory containing practice files.
        output:           Optional JSONL output path.
        collection_name:  ChromaDB collection (default: ``mentor_intelligence``).
    """
    chunks: list[dict] = []
    for file in sorted(practices_dir.rglob("*")):
        if not file.is_file():
            continue
        if file.suffix in {".md", ".txt"}:
            chunks.extend(_parse_text_practice(file, practices_dir))
        elif file.suffix in {".yaml", ".yml"} and HAS_YAML:
            chunks.extend(_parse_yaml_practice(file, practices_dir))

    print(f"Practices parsed: {len(chunks)} chunks from {practices_dir}")

    if not chunks:
        print("  ⚠  No chunks produced. Add .md / .txt / .yaml files to the directory.")
        return []

    # ── Embed ────────────────────────────────────────────────────────────────
    from intelligence_core.embedder import get_embedder
    from intelligence_core.config import settings

    embedder   = get_embedder()
    batch_size = settings.embed_batch_size
    print(f"Embedding {len(chunks)} mentor chunks...")
    for i in range(0, len(chunks), batch_size):
        batch      = chunks[i: i + batch_size]
        embeddings = embedder.embed([c["text"] for c in batch])
        for chunk, emb in zip(batch, embeddings):
            chunk["embedding"] = emb
        print(f"  batch {i // batch_size + 1}: {len(batch)} chunks embedded")

    # Warn if Ollama was down
    zero = sum(
        1 for c in chunks
        if c.get("embedding") and all(v == 0.0 for v in c["embedding"])
    )
    if zero:
        print(f"\n  ⚠  WARNING: {zero}/{len(chunks)} chunks have zero embeddings.")
        print("     Ollama was unreachable. Fix: ollama serve && ollama pull nomic-embed-text\n")

    # ── Write JSONL (optional) ───────────────────────────────────────────────
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(chunk_to_jsonl(c) + "\n")
        print(f"JSONL saved: {output}")

    # ── Load into ChromaDB ───────────────────────────────────────────────────
    from intelligence_core.store import ChromaStore
    store = ChromaStore(collection_name=collection_name)
    store.add(chunks)
    print(f"ChromaDB '{collection_name}': {store.count()} total chunks indexed")

    return chunks


def _parse_text_practice(file: Path, root: Path) -> list[dict]:
    text = file.read_text(encoding="utf-8", errors="replace").strip()
    rel  = str(file.relative_to(root)).replace("\\", "/")
    stem = file.stem
    if len(text) < 30:
        return []

    # Extract H1 as document-level title for context
    doc_title = stem.replace("_", " ").replace("-", " ").title()
    for line in text.splitlines():
        if line.startswith("# ") and not line.startswith("## "):
            doc_title = line[2:].strip()
            break

    # Split by H2 headings → one chunk per section
    sections = _split_by_h2(text, doc_title)

    chunks = []
    for section_title, section_body in sections:
        chunk_text = (
            f"Practice: {doc_title} — {section_title} (from {file.name})\n"
            f"Category: general\n"
            f"---\n{section_body.strip()[:4000]}"
        )
        chunks.append(make_chunk(
            domain="mentor", type_="practice",
            locator=f"practice.{_sanitize(stem)}.{_sanitize(section_title)}",
            text=chunk_text, source=rel, language="markdown",
            metadata={
                "category": "general", "priority": "normal", "audience": ["all"],
                "parent_title": doc_title, "section": section_title,
            },
        ))
    return chunks


def _split_by_h2(text: str, doc_title: str) -> list[tuple[str, str]]:
    """Split markdown by H2 headings. Returns [(section_title, body), ...]."""
    lines = text.splitlines()
    sections: list[tuple[str, str]] = []
    current_title = doc_title          # content before first H2 → intro section
    current_body: list[str] = []

    for line in lines:
        if line.startswith("# ") and not line.startswith("## "):
            # H1 = document title, skip (already captured above)
            continue
        if line.startswith("## "):
            # Flush previous section
            body = "\n".join(current_body).strip()
            if len(body) >= 20:
                sections.append((current_title, body))
            current_title = line[3:].strip()
            current_body = []
        else:
            current_body.append(line)

    # Last section
    body = "\n".join(current_body).strip()
    if len(body) >= 20:
        sections.append((current_title, body))

    # Fallback: whole file as one chunk if no H2 found
    if not sections:
        sections = [(doc_title, text[:4000])]

    return sections


def _parse_yaml_practice(file: Path, root: Path) -> list[dict]:
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
    except Exception:
        return _parse_text_practice(file, root)

    rel           = str(file.relative_to(root)).replace("\\", "/")
    title         = data.get("title", file.stem)
    practice_type = data.get("type", "practice")
    category      = data.get("category", "general")
    priority      = data.get("priority", "normal")
    audience      = data.get("audience", ["all"])
    content       = data.get("content", "")

    if not content or len(str(content)) < 30:
        return []

    chunk_text = (
        f"Practice: {title} (from {file.name})\n"
        f"Category: {category} | Priority: {priority}\n"
        f"---\n{str(content)[:3000]}"
    )
    return [make_chunk(
        domain="mentor", type_=practice_type,
        locator=f"practice.{_sanitize(title)}",
        text=chunk_text, source=rel, language="yaml",
        metadata={"category": category, "priority": priority, "audience": audience},
    )]


def _sanitize(s: str) -> str:
    return re.sub(r"[^\w]", "_", s.lower())[:50]


def main():
    parser = argparse.ArgumentParser(
        description="Ingest practice files and load into ChromaDB"
    )
    parser.add_argument("practices", nargs="?", default="./practices",
                        help="Directory with practice files (default: ./practices)")
    parser.add_argument("-o", "--output", default="mentor_chunks.jsonl",
                        help="JSONL output path (default: mentor_chunks.jsonl)")
    parser.add_argument("--collection", default=COLLECTION_NAME,
                        help=f"ChromaDB collection name (default: {COLLECTION_NAME})")
    args = parser.parse_args()
    ingest_practices(
        Path(args.practices),
        Path(args.output),
        collection_name=args.collection,
    )


if __name__ == "__main__":
    main()
