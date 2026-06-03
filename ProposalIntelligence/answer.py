"""pi-answer — compila un questionario generando risposte in stile.

Per ogni domanda: recupera gli esempi Q&A passati più simili, costruisce un
prompt few-shot di stile e genera la risposta col LLM. Assembla un documento
Markdown con domande, risposte e fonti di stile usate.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from intelligence_core.config import settings
from ProposalIntelligence import COLLECTION_NAME
from ProposalIntelligence.prompts import (
    build_fewshot_context,
    system_prompt_for,
    temperature_for,
)
from ProposalIntelligence.qa_parser import parse_questions


@dataclass
class AnsweredQuestion:
    question: str
    answer: str
    sources: list[dict] = field(default_factory=list)


def _default_retriever():
    from intelligence_core.embedder import get_module_embedder
    from intelligence_core.retriever import Retriever
    from intelligence_core.store import ChromaStore

    return Retriever(
        embedder=get_module_embedder("pi"),
        store=ChromaStore(collection_name=COLLECTION_NAME),
    )


def answer_questions(
    questions: list[str],
    *,
    mode: str = None,
    top_k: int = None,
    retriever=None,
    llm=None,
) -> list[AnsweredQuestion]:
    """Genera le risposte stilizzate per una lista di domande."""
    mode = mode or settings.proposal_mode
    top_k = top_k or settings.proposal_top_k
    retriever = retriever or _default_retriever()
    if llm is None:
        from intelligence_core.llm import get_module_llm_provider
        llm = get_module_llm_provider("pi")

    sys_prompt = system_prompt_for(mode)
    temperature = temperature_for(mode)

    answered: list[AnsweredQuestion] = []
    for q in questions:
        hits = retriever.search(q, top_k=top_k, domain=None)
        context = build_fewshot_context(hits)
        answer = llm.generate(
            q, context, system_prompt=sys_prompt, temperature=temperature
        )
        sources = [
            {
                "source": (getattr(h, "chunk", h) or {}).get("source", ""),
                "score": round(getattr(h, "score", 0.0), 4),
            }
            for h in hits
        ]
        answered.append(AnsweredQuestion(question=q, answer=answer.strip(), sources=sources))
    return answered


def render_markdown(answered: list[AnsweredQuestion], mode: str) -> str:
    """Documento Markdown con domande, risposte e fonti di stile."""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        "# Risposte al questionario",
        "",
        f"> Modalità: **{mode}** · {len(answered)} domande · generato il {today}",
        "",
    ]
    for i, item in enumerate(answered, start=1):
        lines.append(f"## {i}. {item.question}")
        lines.append("")
        lines.append(item.answer or "_(nessuna risposta generata)_")
        lines.append("")
        if item.sources:
            srcs = ", ".join(
                f"{s['source']} ({s['score']})" for s in item.sources if s["source"]
            )
            if srcs:
                lines.append(f"<sub>Fonti di stile: {srcs}</sub>")
                lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def answer_questionnaire(
    questions_path: Path,
    *,
    mode: str = None,
    top_k: int = None,
    output: Path | None = None,
    retriever=None,
    llm=None,
) -> str:
    """Pipeline completa: file questionario → Markdown delle risposte."""
    mode = mode or settings.proposal_mode
    questions = parse_questions(questions_path)
    print(f"Domande estratte: {len(questions)} (modalità: {mode})")
    answered = answer_questions(
        questions, mode=mode, top_k=top_k, retriever=retriever, llm=llm
    )
    md = render_markdown(answered, mode)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        print(f"Output: {output}")
    return md


def main():
    parser = argparse.ArgumentParser(
        description="Compila un questionario generando risposte in stile aziendale"
    )
    parser.add_argument("questions", help="File col questionario (sole domande)")
    parser.add_argument(
        "--mode", choices=("anchored", "commercial"), default=None,
        help="anchored = solo fatti negli esempi · commercial = elaborazione persuasiva",
    )
    parser.add_argument("--top-k", type=int, default=None,
                        help="Quanti esempi Q&A usare come few-shot")
    parser.add_argument("-o", "--output", default="risposte.md")
    args = parser.parse_args()
    answer_questionnaire(
        Path(args.questions),
        mode=args.mode,
        top_k=args.top_k,
        output=Path(args.output),
    )


if __name__ == "__main__":
    main()
