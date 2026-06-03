"""Formatta, salva e confronta i report di valutazione RAGAS."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

Domain = Literal["code", "doc", "mentor"]
EVAL_DIR: Path | None = None  # sentinel; override in tests via monkeypatch.setattr or direct assignment


def _eval_dir() -> Path:
    if EVAL_DIR is not None:
        return EVAL_DIR
    from intelligence_core import paths
    return paths.eval_dir()


def save_report(evaluation: dict, domain: Domain) -> Path:
    d = _eval_dir()
    d.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path = d / f"{timestamp}_{domain}.json"

    payload = {"timestamp": timestamp, "domain": domain, **evaluation}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    # 'latest' come copia, non symlink: i symlink su Windows richiedono privilegi.
    latest = d / f"latest_{domain}.json"
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return path


def load_previous_report(domain: Domain) -> dict | None:
    latest = _eval_dir() / f"latest_{domain}.json"
    if not latest.exists():
        return None
    with open(latest, encoding="utf-8") as f:
        return json.load(f)


def print_report(evaluation: dict, domain: Domain, previous: dict | None = None):
    scores = evaluation["scores"]
    targets = evaluation["targets"]
    passed = evaluation["passed"]

    print(f"\n{'=' * 52}")
    print(f"  RAGAS Evaluation — {domain.upper()}")
    print(f"{'=' * 52}")

    for metric in targets:
        score = scores.get(metric, 0)
        target = targets[metric]
        ok = "✓" if passed[metric] else "✗"
        delta = ""

        if previous:
            prev_score = previous.get("scores", {}).get(metric, 0)
            diff = score - prev_score
            arrow = "↑" if diff > 0.001 else "↓" if diff < -0.001 else "→"
            delta = f"  {arrow} {diff:+.3f}"

        print(f"  {ok} {metric:<22} {score:.3f}  (target ≥ {target:.2f}){delta}")

    overall = "PASS ✓" if evaluation["overall_pass"] else "FAIL ✗"
    print(f"\n  Risultato complessivo: {overall}")
    print(f"{'=' * 52}\n")
