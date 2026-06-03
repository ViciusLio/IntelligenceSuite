"""Calcola i KPI RAGAS sui risultati e li confronta con i target."""

from __future__ import annotations

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

KPI_TARGETS = {
    "faithfulness": 0.75,
    "answer_relevancy": 0.75,
    "context_precision": 0.70,
    "context_recall": 0.68,
}


def evaluate_results(results: list[dict], llm=None, embeddings=None) -> dict:
    dataset = Dataset.from_list(results)

    kwargs = {}
    if llm is not None:
        kwargs["llm"] = llm
    if embeddings is not None:
        kwargs["embeddings"] = embeddings

    scores = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        **kwargs,
    )

    scores_dict = _to_scores_dict(scores)

    evaluation = {
        "scores": scores_dict,
        "targets": KPI_TARGETS,
        "passed": {},
        "overall_pass": True,
    }

    for metric, target in KPI_TARGETS.items():
        score = scores_dict.get(metric, 0)
        passed = score >= target
        evaluation["passed"][metric] = passed
        if not passed:
            evaluation["overall_pass"] = False

    return evaluation


def _to_scores_dict(scores) -> dict:
    """Normalizza l'output di RAGAS in {metric: float}.

    RAGAS 0.2 ritorna un EvaluationResult; nei test è mockato come dict.
    """
    try:
        return {k: float(v) for k, v in dict(scores).items()}
    except (TypeError, ValueError, KeyError):
        # RAGAS 0.2 EvaluationResult: dict(scores) lo itera per indice intero
        # (scores[0] -> KeyError 0). Fallback robusto sulla media per metrica,
        # che ignora i NaN dei sample andati in TimeoutError.
        df = scores.to_pandas()
        return {m: float(df[m].mean()) for m in KPI_TARGETS if m in df.columns}
