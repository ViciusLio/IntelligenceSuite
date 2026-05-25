"""Orchestratore: fonde risposte da CodeIntelligence, DocIntelligence e mentor store."""

from __future__ import annotations
import logging
from dataclasses import dataclass, field

from intelligence_core.retriever import Retriever, RetrievalResult

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
    Riceve una query + contesto sessione.
    Interroga i retriever in base allo step corrente e fonde le risposte.
    Priorità risposta: mentor > doc > code per onboarding.
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
        sources: list[str] = None,
        top_k: int = 5,
    ) -> OrchestratedResult:
        """Fonde risultati da più retriever e genera risposta contestuale."""
        from MentorIntelligence.path_builder import get_current_step, get_next_step, adapt_path

        current_step = get_current_step(session)
        next_step = get_next_step(session)

        # Determina le sorgenti da interrogare
        if sources is None:
            if current_step:
                sources = current_step.get("sources", ["doc", "mentor"])
            else:
                sources = ["doc", "mentor", "code"]

        # Adatta il percorso in base alla domanda
        adapt_path(session, question)

        # Retrieval da tutte le sorgenti selezionate
        results_by_domain: dict[str, list[RetrievalResult]] = {}
        for domain in sources:
            retriever = self.retrievers.get(domain)
            if retriever is None:
                continue
            try:
                results = retriever.search(question, top_k=top_k)
                results_by_domain[domain] = results
            except Exception as e:
                logger.warning("Retriever '%s' fallito: %s", domain, e)
                results_by_domain[domain] = []

        # Reranking unificato cross-domain con priorità mentor > doc > code
        domain_priority = {"mentor": 0.15, "doc": 0.05, "code": 0.0}
        all_results: list[tuple[float, str, RetrievalResult]] = []
        for domain, res_list in results_by_domain.items():
            boost = domain_priority.get(domain, 0.0)
            for r in res_list:
                all_results.append((r.score + boost, domain, r))

        all_results.sort(key=lambda x: x[0], reverse=True)
        top_results = all_results[:top_k]

        # Costruisce contesto per LLM
        context_parts = [r.chunk["text"] for _, _, r in top_results[:3]]
        context = "\n\n---\n\n".join(context_parts)
        confidence = top_results[0][0] if top_results else 0.0

        # Risposta contestuale nel percorso
        step_info = ""
        if current_step:
            step_info = (
                f"\n\n[Sei al passo '{current_step['title']}' del tuo percorso. "
                f"Checkpoint: {current_step.get('checkpoint', '')}]"
            )

        answer = _generate_answer(context, question, session, step_info)

        # Prossima domanda suggerita
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


def _generate_answer(context: str, question: str, session, step_info: str) -> str:
    """Chiama il LLM locale per generare la risposta contestualizzata."""
    import httpx
    from intelligence_core.config import settings
    try:
        prompt = (
            f"Stai aiutando {session.user_name} nel suo onboarding come {session.profile}.\n"
            f"Contesto recuperato:\n{context}\n\n"
            f"Domanda: {question}\n\n"
            "Rispondi in modo chiaro e pratico. "
            "Cita le fonti pertinenti. "
            "Sii conciso ma completo."
            f"{step_info}"
        )
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/generate",
            json={"model": settings.ollama_model, "prompt": prompt, "stream": False},
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip() + step_info
    except Exception as e:
        logger.warning("LLM non disponibile: %s", e)
        return (
            f"[LLM non disponibile — contenuto rilevante trovato]\n\n"
            f"{context[:1000]}{step_info}"
        )
