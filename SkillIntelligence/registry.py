"""SkillRegistry — auto-discovery of Python and Markdown skills."""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import sys
from pathlib import Path

from SkillIntelligence.base import BaseSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Discovers and indexes Skills from Python modules and Markdown files."""

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    # ── loading ───────────────────────────────────────────────────────────────

    def load_python_skills(self, package_path: str | Path | None = None) -> None:
        """Import all modules under SkillIntelligence.skills and register BaseSkill subclasses."""
        import SkillIntelligence.skills as skills_pkg

        pkg_path = package_path or Path(skills_pkg.__file__).parent

        for finder, module_name, _ in pkgutil.iter_modules([str(pkg_path)]):
            full_name = f"SkillIntelligence.skills.{module_name}"
            try:
                mod = importlib.import_module(full_name)
            except Exception as exc:
                logger.warning("SkillRegistry: impossibile importare '%s': %s", full_name, exc)
                continue

            for attr_name in dir(mod):
                obj = getattr(mod, attr_name)
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, BaseSkill)
                    and obj is not BaseSkill
                    and getattr(obj, "name", "")
                ):
                    self._register(obj(), source="python")

    def load_markdown_skills(self, skill_docs_dir: str | Path | None = None) -> None:
        """Parse all .md files under skill_docs/ and register resulting Skills."""
        from SkillIntelligence.parser import parse_skill_markdown

        docs_dir = Path(skill_docs_dir) if skill_docs_dir else Path("skill_docs")
        if not docs_dir.exists():
            logger.info("SkillRegistry: directory '%s' non trovata — nessuna Skill Markdown caricata", docs_dir)
            return

        for md_file in sorted(docs_dir.glob("*.md")):
            try:
                skill = parse_skill_markdown(md_file)
            except Exception as exc:
                logger.warning("SkillRegistry: errore parsing '%s': %s", md_file.name, exc)
                continue
            if skill is not None:
                self._register(skill, source="markdown")

    def _register(self, skill: BaseSkill, source: str) -> None:
        name = skill.name
        if not name:
            logger.warning("SkillRegistry: Skill senza nome ignorata (%s)", type(skill).__name__)
            return

        existing = self._skills.get(name)
        if existing is not None:
            existing_source = existing.source_type()
            # Python always wins over Markdown
            if existing_source == "python":
                logger.info(
                    "SkillRegistry: '%s' da '%s' ignorata — Skill Python già registrata",
                    name, source,
                )
                return
            if source == "python":
                logger.info("SkillRegistry: '%s' Python sovrascrive la versione Markdown", name)
            else:
                logger.warning("SkillRegistry: '%s' Markdown duplicata ignorata", name)
                return

        self._skills[name] = skill
        logger.info("SkillRegistry: registrata '%s' [%s]", name, source)

    # ── public API ────────────────────────────────────────────────────────────

    def get_skill(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def list_skills(self) -> list[dict]:
        return [skill.to_metadata() for skill in self._skills.values()]

    def count(self) -> int:
        return len(self._skills)


# ── module-level singleton, loaded once at server startup ─────────────────────

_registry: SkillRegistry | None = None


def get_registry(
    skill_docs_dir: str | Path | None = None,
    reload: bool = False,
) -> SkillRegistry:
    """Return the module-level SkillRegistry, loading it on first call."""
    global _registry
    if _registry is None or reload:
        _registry = SkillRegistry()
        _registry.load_python_skills()
        _registry.load_markdown_skills(skill_docs_dir)
    return _registry


# ── CLI: si-ingest ─────────────────────────────────────────────────────────────

def ingest_cli() -> None:
    """si-ingest <dir> — validate Markdown Skill files and report."""
    import sys
    from SkillIntelligence.parser import parse_skill_markdown

    target_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("skill_docs")

    if not target_dir.exists():
        print(f"Errore: directory '{target_dir}' non trovata.")
        sys.exit(1)

    md_files = sorted(target_dir.glob("*.md"))
    if not md_files:
        print(f"Nessun file .md trovato in '{target_dir}'.")
        sys.exit(0)

    found = len(md_files)
    valid = 0
    errors: list[str] = []

    for md_file in md_files:
        try:
            skill = parse_skill_markdown(md_file)
            if skill is not None:
                valid += 1
                print(f"  OK  {md_file.name}  →  skill='{skill.name}'  steps={len(skill.steps)}")
            else:
                errors.append(md_file.name)
                print(f"  !!  {md_file.name}  →  non valida (vedi log)")
        except Exception as exc:
            errors.append(md_file.name)
            print(f"  !!  {md_file.name}  →  errore: {exc}")

    print(f"\n{found} Skill trovate, {valid} valide, {len(errors)} errori.")
    if errors:
        sys.exit(1)
