"""Orchestratore: fonde risposte da CodeIntelligence, DocIntelligence e mentor store."""

from __future__ import annotations
import logging
from dataclasses import dataclass, field

from intelligence_core.retriever import Retriever, RetrievalResult
from intelligence_core.llm import get_llm_provider

logger = logging.getLogger(__name__)


@dataclass
class OrchestratedResult:
    answer: str
    sources_by_domain: dict[str, list[RetrievalResult]]
    step_context: dict | None
    suggested_next: str | None
    confidence: float


class MentorOrchestrator:
    """
    Receives a query + session context.
    Queries retrievers according to the current onboarding step,
    merges results cross-domain, and generates a contextual answer
    using the configured LLM provider (Ollama / OpenAI / vLLM / Claude).

    Domain priority for reranking: mentor > doc > code
    """

    def __init__(
        self,
        code_retriever: Retriever,
        doc_retriever: Retriever,
        mentor_retriever: Retriever,
    ):
        self.retrievers = {
            "code":   code_retriever,
            "doc":    doc_retriever,
            "mentor": mentor_retriever,
        }

    def query(
        self,
        question: str,
        session,
        sources: list[str] | None = None,
        top_k: int = 5,
    ) -> OrchestratedResult:
        """Merge results from multiple retrievers and generate a contextual answer."""
        from MentorIntelligence.path_builder import get_current_step, get_next_step, adapt_path

        current_step = get_current_step(session)
        next_step    = get_next_step(session)

        # Decide which domains to query based on the current onboarding step
        if sources is None:
            if current_step:
                sources = current_step.get("sources", ["doc", "mentor"])
            else:
                sources = ["doc", "mentor", "code"]

        # Adapt path based on question content
        adapt_path(session, question)

        # Retrieval across all selected domains
        results_by_domain: dict[str, list[RetrievalResult]] = {}
        for domain in sources:
            retriever = self.retrievers.get(domain)
            if retriever is None:
                continue
            try:
                results_by_domain[domain] = retriever.search(question, top_k=top_k)
            except Exception as exc:
                logger.warning("Retriever '%s' failed: %s", domain, exc)
                results_by_domain[domain] = []

        # Unified cross-domain reranking: mentor > doc > code
        domain_priority = {"mentor": 0.15, "doc": 0.05, "code": 0.0}
        all_results: list[tuple[float, str, RetrievalResult]] = []
        for domain, res_list in results_by_domain.items():
            boost = domain_priority.get(domain, 0.0)
            for r in res_list:
                all_results.append((r.score + boost, domain, r))

        all_results.sort(key=lambda x: x[0], reverse=True)
        top_results = all_results[:top_k]

        # Build context string for LLM
        context_parts = []
        for _, domain, r in top_results[:4]:
            src = r.chunk.get("source", domain)
            context_parts.append(f"[{src}]\n{r.chunk['text']}")
        context    = "\n\n---\n\n".join(context_parts)
        confidence = top_results[0][0] if top_results else 0.0

        # Step annotation (shown to the LLM as context, not appended to output)
        step_context_note = ""
        if current_step:
            step_context_note = (
                f"The user is currently on onboarding step '{current_step['title']}'. "
                f"Checkpoint goal: {current_step.get('checkpoint', 'N/A')}."
            )

        answer = _generate_answer(
            context=context,
            question=question,
            session=session,
            step_context_note=step_context_note,
        )

        # Suggested next question from the following step
        suggested_next = None
        if next_step and next_step.get("suggested_queries"):
            suggested_next = next_step["suggested_queries"][0]

        from MentorIntelligence.session_manager import record_question
        record_question(
            session, question, answer[:200],
            [r.chunk.get("id", "") for _, _, r in top_results[:3]],
        )

        return OrchestratedResult(
            answer=answer,
            sources_by_domain=results_by_domain,
            step_context=current_step,
            suggested_next=suggested_next,
            confidence=confidence,
        )


def _generate_answer(
    context: str,
    question: str,
    session,
    step_context_note: str = "",
) -> str:
    """
    Generate a mentor answer using the configured LLM provider.
    Reads LLM_BACKEND from .env — supports Ollama, OpenAI, vLLM, Claude.
    """
    llm = get_llm_provider()

    system_prompt = (
        f"You are an expert onboarding mentor helping {session.user_name}, "
        f"a new team member with the profile '{session.profile}'.\n"
        "Answer their question using ONLY the provided context. "
        "Be clear, practical, and cite relevant source files when useful. "
        "Be concise but complete. Avoid unnecessary preamble."
    )
    if step_context_note:
        system_prompt += f"\n\nOnboarding context: {step_context_note}"

    if not context.strip():
        return (
            "No relevant documents were found for this question. "
            "Try rephrasing, or make sure the codebase and documents have been indexed."
        )

    try:
        return llm.generate(question, context, system_prompt=system_prompt)
    except Exception as exc:
        logger.warning("LLM generation failed (%s): %s", llm.backend_name, exc)
        return (
            f"[LLM unavailable — most relevant context below]\n\n{context[:1000]}"
        )
