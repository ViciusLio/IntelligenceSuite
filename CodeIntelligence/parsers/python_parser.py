"""Parser Python con AST — estrae funzioni, classi, moduli come chunk leggibili."""

from __future__ import annotations
import ast
import textwrap
from pathlib import Path

from intelligence_core.chunk import make_chunk


def can_parse(path: Path) -> bool:
    return path.suffix == ".py"


def parse_file(path: Path, root: Path) -> list[dict]:
    """Ritorna chunk da file Python via AST. Fallback a chunk raw se il parsing fallisce."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    rel = str(path.relative_to(root)).replace("\\", "/")

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [_raw_chunk(source, rel, path.name)]

    chunks = []
    module_docstring = ast.get_docstring(tree) or ""

    if module_docstring:
        chunks.append(make_chunk(
            domain="code", type_="module",
            locator=f"{_stem(rel)}.module",
            text=f"Module: {path.name} (in {rel})\nDocstring: {module_docstring}",
            source=rel, language="python",
            metadata={"file": rel},
        ))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            chunk = _function_chunk(node, source, rel)
            if chunk:
                chunks.append(chunk)
        elif isinstance(node, ast.ClassDef):
            chunk = _class_chunk(node, source, rel)
            if chunk:
                chunks.append(chunk)

    if not chunks:
        chunks.append(_raw_chunk(source, rel, path.name))

    return chunks


def _stem(rel: str) -> str:
    return rel.replace("/", ".").replace("\\", ".").removesuffix(".py")


def _function_chunk(node: ast.FunctionDef, source: str, rel: str) -> dict | None:
    name = node.name
    docstring = ast.get_docstring(node) or ""
    args = _format_args(node.args)
    returns = ""
    if node.returns:
        try:
            returns = f" -> {ast.unparse(node.returns)}"
        except Exception:
            pass

    lines = source.splitlines()
    body_lines = lines[node.body[0].lineno - 1: node.end_lineno]
    body_preview = "\n".join(body_lines[:20])
    if len(body_lines) > 20:
        body_preview += f"\n    ... ({len(body_lines) - 20} righe omesse)"

    text = (
        f"Function: {name} (in {rel})\n"
        f"Signature: def {name}({args}){returns}\n"
    )
    if docstring:
        text += f"Docstring: {docstring}\n"
    text += f"Body:\n{textwrap.indent(body_preview, '    ')}"

    if len(text.strip()) < 20:
        return None

    locator = f"{_stem(rel)}.{name}"
    return make_chunk(
        domain="code", type_="function", locator=locator,
        text=text, source=rel, language="python",
        metadata={
            "line_start": node.lineno,
            "line_end":   node.end_lineno,
            "is_async":   isinstance(node, ast.AsyncFunctionDef),
            "class":      None,
        },
    )


def _class_chunk(node: ast.ClassDef, source: str, rel: str) -> dict | None:
    name = node.name
    docstring = ast.get_docstring(node) or ""
    bases = []
    for b in node.bases:
        try:
            bases.append(ast.unparse(b))
        except Exception:
            bases.append("?")

    methods = [
        n.name for n in ast.walk(node)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.col_offset > node.col_offset
    ]

    text = f"Class: {name} (in {rel})\n"
    if bases:
        text += f"Inherits: {', '.join(bases)}\n"
    if docstring:
        text += f"Docstring: {docstring}\n"
    if methods:
        text += f"Methods: {', '.join(methods[:15])}"
        if len(methods) > 15:
            text += f" ... ({len(methods) - 15} altri)"

    if len(text.strip()) < 20:
        return None

    locator = f"{_stem(rel)}.{name}"
    return make_chunk(
        domain="code", type_="class", locator=locator,
        text=text, source=rel, language="python",
        metadata={
            "line_start":   node.lineno,
            "line_end":     node.end_lineno,
            "base_classes": bases,
        },
    )


def _raw_chunk(source: str, rel: str, filename: str) -> dict:
    preview = source[:2000]
    text = f"File: {filename} (in {rel})\n---\n{preview}"
    return make_chunk(
        domain="code", type_="file", locator=_stem(rel),
        text=text, source=rel, language="python",
        metadata={"raw": True},
    )


def _format_args(args: ast.arguments) -> str:
    parts = []
    for arg in args.args:
        annotation = ""
        if arg.annotation:
            try:
                annotation = f": {ast.unparse(arg.annotation)}"
            except Exception:
                pass
        parts.append(f"{arg.arg}{annotation}")
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    return ", ".join(parts)
