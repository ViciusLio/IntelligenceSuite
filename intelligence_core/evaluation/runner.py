"""Esegue le domande del testset sul sistema reale di Intelligence Suite.

Usa il Retriever (ChromaDB + embedder) e il provider LLM del progetto.
"""

from __future__ import annotations

from typing import Literal

from intelligence_core.evaluation.paths import get_collection

Domain = Literal["code", "doc", "mentor"]


def run_testset(
    testset: list[dict],
    domain: Domain,
    top_k: int = 5,
) -> list[dict]:
    from intelligence_core.llm import get_llm_provider
    from intelligence_core.retriever import Retriever

    retriever = Retriever.load_default(collection_name=get_collection(domain))
    llm = get_llm_provider()

    results = []
    total = len(testset)

    for i, row in enumerate(testset, 1):
        question = row["question"]
        print(f"  [{i}/{total}] {question[:60]}...")

        retrieved = retriever.search(query=question, top_k=top_k, domain=domain)
        contexts = [r.chunk["text"] for r in retrieved]
        context_str = "\n\n---\n\n".join(contexts)

        answer = llm.generate(question=question, context=context_str)

        results.append(
            {
                "question": question,
                "answer": answer,
                "contexts": contexts,
                "ground_truth": row.get("ground_truth", ""),
            }
        )

    return results
