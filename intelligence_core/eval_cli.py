"""CLI ci-eval: valuta la qualità del RAG con RAGAS."""

from __future__ import annotations

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Valuta la qualità del RAG con RAGAS")
    parser.add_argument("--domain", choices=["code", "doc", "mentor"], default="code")
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--regenerate", action="store_true")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--max-docs",
        type=int,
        default=150,
        help="Tetto di documenti per il knowledge graph RAGAS (default 150). "
        "Valori alti su corpus grandi fanno esplodere find_indirect_clusters.",
    )
    args = parser.parse_args()

    print(
        "Avvio RAGAS evaluation… caricamento moduli "
        "(il primo import può richiedere ~20-60s)",
        flush=True,
    )

    from intelligence_core.evaluation.evaluator import evaluate_results
    from intelligence_core.evaluation.generator import generate_testset
    from intelligence_core.evaluation.ragas_factory import (
        get_ragas_embeddings,
        get_ragas_llm,
    )
    from intelligence_core.evaluation.report import (
        load_previous_report,
        print_report,
        save_report,
    )
    from intelligence_core.evaluation.runner import run_testset

    print(f"\nRAGAS Evaluation — dominio: {args.domain}")
    print(f"Campioni: {args.samples}, top-k: {args.top_k}\n")

    testset = generate_testset(
        domain=args.domain,
        test_size=args.samples,
        force_regenerate=args.regenerate,
        max_docs=args.max_docs,
    )

    results = run_testset(testset=testset, domain=args.domain, top_k=args.top_k)

    evaluation = evaluate_results(
        results,
        llm=get_ragas_llm(),
        embeddings=get_ragas_embeddings(),
    )
    previous = load_previous_report(args.domain)
    print_report(evaluation, args.domain, previous)

    path = save_report(evaluation, args.domain)
    print(f"Report salvato: {path}")

    sys.exit(0 if evaluation["overall_pass"] else 1)


if __name__ == "__main__":
    main()
