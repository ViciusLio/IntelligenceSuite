"""SkillExecutor — step-by-step guidance with cross-domain retrieval."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from SkillIntelligence.base import (
    BaseSkill,
    Domain,
    SkillContext,
    SkillResult,
    SkillStep,
    VALID_DOMAINS,
)
# Top-level import so tests can patch SkillIntelligence.executor.get_registry
from SkillIntelligence.registry import get_registry

logger = logging.getLogger(__name__)

# Session storage dir — sentinel; tests can override via monkeypatch.setattr or sessions_dir arg
_SESSIONS_DIR: Path | None = None

# Valid domains; collection names resolved at runtime via paths.collection_name()
_DOMAIN_COLLECTIONS: dict[str, str] = {
    "code":   "code_intelligence",
    "doc":    "doc_intelligence",
    "mentor": "mentor_intelligence",
}


def _sessions_dir_default() -> Path:
    if _SESSIONS_DIR is not None:
        return _SESSIONS_DIR
    from intelligence_core import paths
    return paths.skill_sessions_dir()

# Max tokens (chars) of retrieved context passed to the LLM
_MAX_CONTEXT_CHARS = 12000  # approx 3000 tokens at ~4 chars/token


class SkillExecutor:
    """Drives a SkillSession step by step, persisting state to disk."""

    def __init__(
        self,
        llm=None,
        sessions_dir: Path | None = None,
        retriever_factory=None,
        registry=None,
    ) -> None:
        """
        Args:
            llm: LLMProvider instance (optional — loaded lazily from settings).
            sessions_dir: Override for session storage directory.
            retriever_factory: callable(collection_name) → Retriever (injectable for tests).
            registry: SkillRegistry override — if set, used instead of the module singleton.
                      Injected by tests to avoid the global registry/disk side-effects.
        """
        self._llm = llm
        self._sessions_dir = sessions_dir or _sessions_dir_default()
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        # DECISION: retriever_factory and registry are injectable so tests can mock
        # without needing a live ChromaDB instance or the global registry singleton.
        self._retriever_factory = retriever_factory or self._default_retriever_factory
        self._registry_override = registry

    # ── public API ────────────────────────────────────────────────────────────

    def start_session(
        self, skill: BaseSkill, parameters: dict[str, Any]
    ) -> tuple[str, SkillResult]:
        """Create a new session and execute the first step."""
        errors = skill.validate_parameters(parameters)
        if errors:
            raise ValueError(f"Parametri non validi: {'; '.join(errors)}")

        session_id = str(uuid.uuid4())
        context = SkillContext(
            skill_name=skill.name,
            parameters=parameters,
            completed_steps=[],
            step_outputs={},
            current_step_index=0,
        )
        self._save_session(session_id, skill, context)

        result = self._execute_step(skill, skill.steps[0], context, session_id)
        return session_id, result

    def next_step(self, session_id: str, user_input: str | None = None) -> SkillResult | None:
        """Advance to the next step. Returns None when the session is completed."""
        skill, context = self._load_session(session_id)

        # record user_input on the last completed step if provided
        if user_input and context.completed_steps:
            last_id = context.completed_steps[-1]
            context.step_outputs[last_id] = (
                context.step_outputs.get(last_id, "") + f"\n[Utente]: {user_input}"
            )

        context.current_step_index += 1
        if context.current_step_index >= len(skill.steps):
            self._delete_session(session_id)
            return None

        self._save_session(session_id, skill, context)
        return self._execute_step(skill, skill.steps[context.current_step_index], context, session_id)

    def get_session_info(self, session_id: str) -> dict:
        """Return current session metadata without advancing."""
        skill, context = self._load_session(session_id)
        return {
            "skill_name":      context.skill_name,
            "parameters":      context.parameters,
            "steps_completed": len(context.completed_steps),
            "current_step":    context.current_step_index,
            "total_steps":     len(skill.steps),
            "status":          "in_progress",
        }

    # ── internal execution ────────────────────────────────────────────────────

    def _execute_step(
        self,
        skill: BaseSkill,
        step: SkillStep,
        context: SkillContext,
        session_id: str,
    ) -> SkillResult:
        query = self._interpolate(step.knowledge_query, context.parameters)

        # Retrieve chunks from the relevant domains
        search_results = self._retrieve_cross_domain(query, step.domains)

        # Build context string for the LLM
        llm_context = self._build_llm_context(step, context, search_results)

        # Generate guidance
        guidance = self._generate_guidance(step, context, llm_context)

        # Update session state
        context.completed_steps.append(step.id)
        context.step_outputs[step.id] = guidance

        is_last = context.current_step_index >= len(skill.steps) - 1
        self._save_session(session_id, skill, context)

        sources = [
            {
                "id":     r.chunk.get("id", ""),
                "source": r.chunk.get("source", ""),
                "type":   r.chunk.get("type", ""),
                "score":  round(r.score, 4),
                "domain": r.chunk.get("domain", ""),
            }
            for r in search_results
        ]

        return SkillResult(
            step_id=step.id,
            title=step.title,
            guidance=guidance,
            sources=sources,
            requires_confirmation=step.requires_confirmation,
            is_last_step=is_last,
            session_id=session_id,
        )

    def _retrieve_cross_domain(
        self,
        query: str,
        domains: list[Domain],
        top_k: int = 5,
    ) -> list:
        """Retrieve from one or more domain collections, merge by score, deduplicate."""
        from intelligence_core.retriever import RetrievalResult

        # Resolve domain list
        effective_domains: list[str]
        if "all" in domains:
            effective_domains = list(_DOMAIN_COLLECTIONS.keys())
        else:
            effective_domains = [d for d in domains if d in _DOMAIN_COLLECTIONS]

        if not effective_domains:
            return []

        all_results: list[RetrievalResult] = []
        seen_sources: set[str] = set()

        from intelligence_core import paths as _paths
        for domain in effective_domains:
            collection = _paths.collection_name(domain)
            try:
                retriever = self._retriever_factory(collection)
                results = retriever.search(query, top_k=top_k)
                all_results.extend(results)
            except Exception as exc:
                logger.warning("SkillExecutor: retrieval fallito per dominio '%s': %s", domain, exc)

        # Sort by score descending
        all_results.sort(key=lambda r: r.score, reverse=True)

        # Deduplicate by source path
        deduped: list[RetrievalResult] = []
        for r in all_results:
            src = r.chunk.get("source", "")
            if src not in seen_sources:
                seen_sources.add(src)
                deduped.append(r)
            if len(deduped) >= top_k:
                break

        return deduped

    def _build_llm_context(
        self,
        step: SkillStep,
        context: SkillContext,
        search_results: list,
    ) -> str:
        parts: list[str] = []

        if search_results:
            chunk_texts = []
            for r in search_results:
                src = r.chunk.get("source", "unknown")
                chunk_texts.append(f"[{src}]\n{r.chunk['text']}")
            retrieved = "\n\n---\n\n".join(chunk_texts)
            # Truncate to avoid token overflow
            if len(retrieved) > _MAX_CONTEXT_CHARS:
                retrieved = retrieved[:_MAX_CONTEXT_CHARS] + "\n[... troncato ...]"
            parts.append(f"CONTESTO RECUPERATO DAL KNOWLEDGE BASE:\n{retrieved}")
        else:
            parts.append("CONTESTO RECUPERATO DAL KNOWLEDGE BASE:\n(nessun documento trovato)")

        params_text = "\n".join(f"  {k}: {v}" for k, v in context.parameters.items())
        parts.append(f"PARAMETRI DELL'UTENTE:\n{params_text}")

        if context.step_outputs:
            prev = "\n\n".join(
                f"[{sid}]: {output[:600]}"
                for sid, output in context.step_outputs.items()
            )
            parts.append(f"STEP GIÀ COMPLETATI:\n{prev}")

        return "\n\n".join(parts)

    def _generate_guidance(
        self,
        step: SkillStep,
        context: SkillContext,
        llm_context: str,
    ) -> str:
        prompt = (
            f"Sei un assistente esperto che guida un utente attraverso una procedura aziendale.\n\n"
            f"SKILL: {context.skill_name}\n"
            f"STEP CORRENTE: {step.title}\n"
            f"OBIETTIVO DEL STEP: {step.description}\n\n"
            f"{llm_context}\n\n"
            f"Fornisci una guida chiara e contestuale per questo step specifico.\n"
            f"Cita le informazioni rilevanti trovate nel knowledge base.\n"
            f"Sii concreto e actionable. Non inventare informazioni non presenti nel contesto.\n"
            f"Rispondi nella lingua dell'utente."
        )
        llm = self._get_llm()
        try:
            return llm.generate(prompt, "")
        except Exception as exc:
            logger.error("SkillExecutor: LLM generation fallita: %s", exc)
            return f"[Errore generazione guidance: {exc}]"

    # ── session persistence ───────────────────────────────────────────────────

    def _session_path(self, session_id: str) -> Path:
        return self._sessions_dir / f"{session_id}.json"

    def _save_session(self, session_id: str, skill: BaseSkill, context: SkillContext) -> None:
        data = {
            "skill_name":          skill.name,
            "parameters":          context.parameters,
            "completed_steps":     context.completed_steps,
            "step_outputs":        context.step_outputs,
            "current_step_index":  context.current_step_index,
        }
        self._session_path(session_id).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _load_session(self, session_id: str) -> tuple[BaseSkill, SkillContext]:
        path = self._session_path(session_id)
        if not path.exists():
            raise KeyError(f"Sessione non trovata: {session_id}")
        data = json.loads(path.read_text(encoding="utf-8"))

        registry = self._registry_override or get_registry()
        skill = registry.get_skill(data["skill_name"])
        if skill is None:
            raise KeyError(f"Skill '{data['skill_name']}' non trovata nel registry")

        context = SkillContext(
            skill_name=data["skill_name"],
            parameters=data["parameters"],
            completed_steps=data["completed_steps"],
            step_outputs=data["step_outputs"],
            current_step_index=data["current_step_index"],
        )
        return skill, context

    def _delete_session(self, session_id: str) -> None:
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _interpolate(template: str, params: dict[str, Any]) -> str:
        for key, value in params.items():
            template = template.replace(f"{{{key}}}", str(value))
        return template

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        from intelligence_core.llm import get_llm_provider
        self._llm = get_llm_provider()
        return self._llm

    @staticmethod
    def _default_retriever_factory(collection_name: str):
        from intelligence_core.retriever import Retriever
        return Retriever.load_default(collection_name=collection_name)
