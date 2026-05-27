"""Markdown → Skill parser (rule-based, zero LLM dependency)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from SkillIntelligence.base import BaseSkill, Domain, SkillStep, VALID_DOMAINS

logger = logging.getLogger(__name__)

# ── regex patterns ────────────────────────────────────────────────────────────
_RE_SKILL_TITLE   = re.compile(r"^#\s+Skill:\s+(.+)$", re.IGNORECASE)
_RE_META_LINE     = re.compile(r"^>\s+(\w+):\s+(.+)$")
_RE_STEP_HEADING  = re.compile(r"^##\s+Step\s+\d+[:\-]?\s+(.+)$", re.IGNORECASE)
_RE_DOMAINS_LINE  = re.compile(r"^\*\*Domini[:\*]*\*+\s*:?\s*(.+)$", re.IGNORECASE)
_RE_QUERY_LINE    = re.compile(r"^\*\*Query[:\*]*\*+\s*:?\s*(.+)$", re.IGNORECASE)

# ── parameter spec parser ────────────────────────────────────────────────────

def _parse_param_spec(raw: str) -> dict[str, dict]:
    """Parse 'name (type, required, enum: a|b)' declarations."""
    params: dict[str, dict] = {}
    for part in raw.split(","):
        part = part.strip()
        # Each declaration: param_name (type, required, enum: val|val)
        m = re.match(r"(\w+)\s*(?:\(([^)]*)\))?", part)
        if not m:
            continue
        param_name = m.group(1).strip()
        if not param_name:
            continue
        spec_raw = m.group(2) or ""
        spec: dict[str, Any] = {}
        # type
        type_m = re.search(r"\bstr\b|\bint\b|\bfloat\b|\bbool\b", spec_raw)
        spec["type"] = type_m.group(0) if type_m else "str"
        # required
        spec["required"] = "required" in spec_raw.lower()
        # enum
        enum_m = re.search(r"enum[:\s]+([^\s,)]+)", spec_raw, re.IGNORECASE)
        if enum_m:
            spec["enum"] = [v.strip() for v in enum_m.group(1).split("|") if v.strip()]
        params[param_name] = spec
    return params


# ── snake_case helper ────────────────────────────────────────────────────────

def _to_snake_case(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", "_", text)


# ── MarkdownSkill (dynamic subclass) ────────────────────────────────────────

def _build_skill_class(
    name: str,
    description: str,
    parameters: dict[str, dict],
    steps: list[SkillStep],
) -> type:
    """Create a BaseSkill subclass dynamically from parsed Markdown data."""
    return type(
        f"MarkdownSkill_{name}",
        (BaseSkill,),
        {
            "name": name,
            "description": description,
            "parameters": parameters,
            "steps": steps,
            "source_type": classmethod(lambda cls: "markdown"),
        },
    )


# ── main parse function ──────────────────────────────────────────────────────

def parse_skill_markdown(path: str | Path) -> BaseSkill | None:
    """
    Parse a Markdown file into a BaseSkill instance.

    Returns None (with a logged warning) if the file is invalid.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("SkillParser: cannot read '%s': %s", path, exc)
        return None

    lines = text.splitlines()

    skill_name: str | None = None
    description: str = ""
    parameters: dict[str, dict] = {}
    steps: list[SkillStep] = []

    # state machine
    current_step_title: str | None = None
    current_domains: list[Domain] = []
    current_query: str = ""
    current_desc_lines: list[str] = []

    def _flush_step():
        nonlocal current_step_title, current_domains, current_query, current_desc_lines
        if current_step_title is None:
            return
        step_id = f"step_{len(steps) + 1}"
        query = current_query.strip() or current_step_title
        domains: list[Domain] = current_domains if current_domains else ["doc"]
        step_desc = " ".join(current_desc_lines).strip() or current_step_title
        steps.append(SkillStep(
            id=step_id,
            title=current_step_title,
            description=step_desc,
            knowledge_query=query,
            domains=domains,
        ))
        current_step_title = None
        current_domains = []
        current_query = ""
        current_desc_lines = []

    for line in lines:
        # skill title
        m = _RE_SKILL_TITLE.match(line)
        if m:
            skill_name = _to_snake_case(m.group(1))
            continue

        # meta lines (description / parameters) — only before first step
        if not steps and current_step_title is None:
            m = _RE_META_LINE.match(line)
            if m:
                key, value = m.group(1).lower(), m.group(2).strip()
                if key == "description":
                    description = value
                elif key == "parameters":
                    parameters = _parse_param_spec(value)
                continue

        # step heading
        m = _RE_STEP_HEADING.match(line)
        if m:
            _flush_step()
            current_step_title = m.group(1).strip()
            continue

        if current_step_title is not None:
            # domains line
            m = _RE_DOMAINS_LINE.match(line)
            if m:
                raw_domains = [d.strip().lower() for d in m.group(1).split(",")]
                valid: list[Domain] = [d for d in raw_domains if d in VALID_DOMAINS]  # type: ignore[misc]
                invalid = [d for d in raw_domains if d not in VALID_DOMAINS]
                if invalid:
                    logger.warning(
                        "SkillParser '%s': domini non validi ignorati: %s", path.name, invalid
                    )
                current_domains = valid if valid else ["doc"]
                continue

            # query line
            m = _RE_QUERY_LINE.match(line)
            if m:
                current_query = m.group(1).strip()
                continue

            # free text → description
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                current_desc_lines.append(stripped)

    _flush_step()

    # ── validation ────────────────────────────────────────────────────────────
    if not skill_name:
        logger.warning("SkillParser: '%s' ignorato — manca il titolo '# Skill:'", path.name)
        return None

    if not steps:
        logger.warning("SkillParser: '%s' ignorato — nessuno step trovato", path.name)
        return None

    for step in steps:
        if not step.knowledge_query:
            logger.warning(
                "SkillParser: '%s' step '%s' — knowledge_query vuota, uso titolo",
                path.name, step.id,
            )
            step.knowledge_query = step.title

    cls = _build_skill_class(skill_name, description, parameters, steps)
    instance = cls()
    logger.info("SkillParser: caricata Skill '%s' da '%s' (%d step)", skill_name, path.name, len(steps))
    return instance
