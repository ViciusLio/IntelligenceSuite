"""is-eval — Evaluation pipeline for IntelligenceSuite RAG quality.

Usage:
    is-eval C:/path/to/ci-bench-L1
    is-eval C:/path/to/ci-bench-L2 --collection code_intelligence --top-k 5
    is-eval C:/path/to/ci-bench-L1 -o results_L1.json
"""

from __future__ import annotations
import argparse
import json
import math
import time
from pathlib import Path


# ── Metric helpers ────────────────────────────────────────────────────────────

def _norm(path: str) -> str:
    return path.replace("\\", "/").lower()


def _rank_of_hit(
    sources: list[str],
    texts: list[str],
    expected_file: str,
    expected_symbols: list[str],
) -> int | None:
    """Return 1-based rank of first relevant chunk, or None if not found."""
    ef = _norm(expected_file) if expected_file else ""
    for i, (src, txt) in enumerate(zip(sources, texts)):
        src_n = _norm(src)
        if ef and (ef in src_n or src_n.endswith(ef)):
            return i + 1
        if any(sym in txt for sym in expected_symbols):
            return i + 1
    return None


def _ndcg(
    sources: list[str],
    texts: list[str],
    expected_file: str,
    expected_symbols: list[str],
    k: int = 5,
) -> float:
    """NDCG@k with binary single-relevant-doc assumption."""
    rank = _rank_of_hit(sources[:k], texts[:k], expected_file, expected_symbols)
    if rank is None:
        return 0.0
    dcg  = 1.0 / math.log2(rank + 1)
    idcg = 1.0 / math.log2(2)          # ideal: relevant at rank 1
    return min(dcg / idcg, 1.0)


# ── Core eval loop ────────────────────────────────────────────────────────────

def run_eval(
    ground_truth_path: Path,
    collection_name: str = "code_intelligence",
    top_k: int = 5,
) -> tuple[dict, dict, list[dict]]:
    """Run evaluation against a ground_truth.json and return (metrics, by_category, per_query)."""
    from intelligence_core.retriever import Retriever

    retriever = Retriever.load_default(collection_name=collection_name)

    with ground_truth_path.open(encoding="utf-8") as f:
        gt = json.load(f)

    queries    = gt.get("queries", [])
    repo       = gt.get("repo", ground_truth_path.parent.parent.name)
    difficulty = gt.get("difficulty", "?")

    print(f"\n{'═' * 64}")
    print(f"  Benchmark  : {repo}  [{difficulty}]")
    print(f"  Queries    : {len(queries)}  |  collection: {collection_name}  |  top_k: {top_k}")
    print(f"{'═' * 64}")

    per_query: list[dict] = []
    latencies: list[float] = []

    for idx, q in enumerate(queries, 1):
        question = q.get("question") or q.get("query", "")
        t0 = time.perf_counter()
        retrieved  = retriever.search(question, top_k=top_k)
        latency_ms = (time.perf_counter() - t0) * 1000
        latencies.append(latency_ms)

        sources = [r.chunk.get("source", "") for r in retrieved]
        texts   = [r.chunk.get("text",   "") for r in retrieved]
        ef      = q.get("expected_primary_file", "")
        syms    = q.get("expected_symbols", [])

        rank = _rank_of_hit(sources, texts, ef, syms)

        per_query.append({
            "id":         q.get("id", f"Q{idx:03d}"),
            "question":   question,
            "category":   q.get("category", ""),
            "difficulty": q.get("difficulty", ""),
            "hit_at_1":   rank == 1,
            "hit_at_3":   rank is not None and rank <= 3,
            "hit_at_5":   rank is not None and rank <= top_k,
            "mrr":        1.0 / rank if rank else 0.0,
            "ndcg_at_5":  _ndcg(sources, texts, ef, syms, k=min(5, top_k)),
            "latency_ms": latency_ms,
            "rank":       rank,
            "top_sources": sources[:3],
        })

        marker = "✓" if rank else "✗"
        rank_s = f"@{rank}" if rank else "miss"
        print(f"  {marker} {q.get('id','?'):>10}  {rank_s:<6}  {latency_ms:>6.0f}ms  {question[:55]}")

    # ── Aggregate ─────────────────────────────────────────────────────────────
    n          = len(per_query)
    lat_sorted = sorted(latencies)
    metrics = {
        "hit_at_1":       sum(r["hit_at_1"]   for r in per_query) / n,
        "hit_at_3":       sum(r["hit_at_3"]   for r in per_query) / n,
        "hit_at_5":       sum(r["hit_at_5"]   for r in per_query) / n,
        "mrr":            sum(r["mrr"]         for r in per_query) / n,
        "ndcg_at_5":      sum(r["ndcg_at_5"]  for r in per_query) / n,
        "latency_p50_ms": lat_sorted[n // 2],
        "latency_p99_ms": lat_sorted[max(0, int(n * 0.99) - 1)],
        "n_queries":      n,
    }

    # ── By category ────────────────────────────────────────────────────────────
    cats = sorted(set(r["category"] for r in per_query if r["category"]))
    by_category: dict[str, dict] = {}
    for cat in cats:
        cr = [r for r in per_query if r["category"] == cat]
        nc = len(cr)
        by_category[cat] = {
            "n":        nc,
            "hit_at_5": sum(r["hit_at_5"]  for r in cr) / nc,
            "mrr":      sum(r["mrr"]        for r in cr) / nc,
            "ndcg_at_5":sum(r["ndcg_at_5"] for r in cr) / nc,
        }

    return metrics, by_category, per_query


# ── Report printing ───────────────────────────────────────────────────────────

def _print_report(metrics: dict, by_category: dict, per_query: list[dict]) -> None:
    n = metrics.get("n_queries", len(per_query))

    print(f"\n{'─' * 64}")
    print(f"  {'Metrica':<24} {'Valore':>10}")
    print(f"  {'─' * 36}")
    for k, v in metrics.items():
        if k == "n_queries":
            continue
        if "latency" in k:
            print(f"  {k:<24} {v:>9.0f}ms")
        else:
            print(f"  {k:<24} {v:>10.1%}")

    if by_category:
        print(f"\n  {'Categoria':<28} {'N':>4} {'Hit@5':>8} {'MRR':>8} {'NDCG@5':>8}")
        print(f"  {'─' * 60}")
        for cat, m in by_category.items():
            print(f"  {cat:<28} {m['n']:>4} {m['hit_at_5']:>8.1%} {m['mrr']:>8.1%} {m['ndcg_at_5']:>8.1%}")

    misses = [r for r in per_query if not r["hit_at_5"]]
    hits   = n - len(misses)
    print(f"\n  Totale: {hits}/{n} hit entro top-{per_query[0]['hit_at_5'] and 5 or 5}")

    if misses:
        print(f"  Missed ({len(misses)}):")
        for r in misses:
            diff = f"[{r['difficulty']}]" if r.get("difficulty") else ""
            cat  = r.get("category", "")
            print(f"    ✗  {r['id']:>10}  {diff:<8}  {cat:<22}  {r['question'][:45]}")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Valuta la qualità RAG su benchmark strutturati (ground_truth.json)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  is-eval C:/path/to/ci-bench-L1
  is-eval C:/path/to/ci-bench-L2 --top-k 10
  is-eval C:/path/to/ci-bench-L1 -o results_L1.json
  is-eval C:/path/to/ci-bench-L1 C:/path/to/ci-bench-L2 C:/path/to/ci-bench-L3
        """,
    )
    ap.add_argument(
        "bench", nargs="+",
        help="Path a una o più repo di benchmark (devono contenere benchmarks/ground_truth.json)",
    )
    ap.add_argument(
        "--collection", default="code_intelligence",
        help="ChromaDB collection da interrogare (default: code_intelligence)",
    )
    ap.add_argument(
        "--top-k", type=int, default=5, metavar="K",
        help="Numero di chunk da recuperare per query (default: 5)",
    )
    ap.add_argument(
        "--output", "-o",
        help="Salva il report completo in formato JSON (per più repo usa un file per repo)",
    )
    args = ap.parse_args()

    all_metrics: list[dict] = []

    for bench_path in args.bench:
        gt_path = Path(bench_path) / "benchmarks" / "ground_truth.json"
        if not gt_path.exists():
            print(f"  ✗ ground_truth.json non trovato: {gt_path}")
            continue

        metrics, by_category, per_query = run_eval(gt_path, args.collection, args.top_k)
        _print_report(metrics, by_category, per_query)
        all_metrics.append({"bench": bench_path, **metrics})

        if args.output and len(args.bench) == 1:
            out = {"metrics": metrics, "by_category": by_category, "per_query": per_query}
            Path(args.output).write_text(
                json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"  Report salvato: {args.output}\n")

    # ── Summary se più repo ────────────────────────────────────────────────────
    if len(all_metrics) > 1:
        print(f"\n{'═' * 64}")
        print(f"  RIEPILOGO — {len(all_metrics)} benchmark")
        print(f"  {'Repo':<30} {'Hit@5':>8} {'MRR':>8} {'NDCG@5':>8}")
        print(f"  {'─' * 56}")
        for m in all_metrics:
            name = Path(m["bench"]).name
            print(f"  {name:<30} {m['hit_at_5']:>8.1%} {m['mrr']:>8.1%} {m['ndcg_at_5']:>8.1%}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
