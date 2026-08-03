"""Shared metrics for O/U 2.5 regime mining."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Sequence

from worldcup_predictor.research.true_forward_472_evaluation.metrics import (
    accuracy_pack,
    priced_performance,
    timing_stage,
    wilson_interval,
)

__all__ = [
    "accuracy_pack",
    "priced_performance",
    "timing_stage",
    "wilson_interval",
    "config_hash",
    "lambda_bucket",
    "prob_bucket",
    "goals_to_ou",
    "norm_ou",
    "score_total",
]


def config_hash(payload: dict[str, Any]) -> str:
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def lambda_bucket(total: float | None) -> str:
    if total is None:
        return "MISSING"
    x = float(total)
    if x < 1.6:
        return "<1.6"
    if x < 1.9:
        return "1.6-1.89"
    if x < 2.2:
        return "1.9-2.19"
    if x < 2.5:
        return "2.2-2.49"
    if x < 2.8:
        return "2.5-2.79"
    if x < 3.2:
        return "2.8-3.19"
    if x < 3.6:
        return "3.2-3.59"
    return ">=3.6"


def prob_bucket(p: float | None) -> str:
    if p is None:
        return "MISSING"
    x = float(p)
    if x > 1.0:
        x = x / 100.0
    pct = x * 100.0
    if pct < 50:
        return "<50%"
    if pct < 55:
        return "50-54.99%"
    if pct < 60:
        return "55-59.99%"
    if pct < 65:
        return "60-64.99%"
    if pct < 70:
        return "65-69.99%"
    if pct < 75:
        return "70-74.99%"
    return ">=75%"


def norm_ou(value: Any) -> str | None:
    if value is None:
        return None
    t = str(value).lower().strip().replace(".", "_").replace(" ", "_")
    mapping = {
        "over": "over_2_5",
        "over_2_5": "over_2_5",
        "over_25": "over_2_5",
        "o": "over_2_5",
        "under": "under_2_5",
        "under_2_5": "under_2_5",
        "under_25": "under_2_5",
        "u": "under_2_5",
    }
    return mapping.get(t)


def goals_to_ou(home: int | None, away: int | None) -> str | None:
    if home is None or away is None:
        return None
    return "over_2_5" if int(home) + int(away) > 2 else "under_2_5"


def score_total(score: str | None) -> int | None:
    if not score or "-" not in str(score):
        return None
    try:
        h, a = str(score).split("-", 1)
        return int(h) + int(a)
    except ValueError:
        return None


def remove_one_win_sensitivity(hits: Sequence[bool]) -> dict[str, Any]:
    n = len(hits)
    base_hits = sum(1 for h in hits if h)
    base_acc = base_hits / n if n else None
    if n <= 1 or base_hits == 0:
        return {"base_accuracy": base_acc, "min_after_remove_1": base_acc, "collapses": False}
    # remove one win at a time
    mins = []
    win_idxs = [i for i, h in enumerate(hits) if h]
    for i in win_idxs:
        rem = [h for j, h in enumerate(hits) if j != i]
        mins.append(sum(1 for h in rem if h) / len(rem))
    min_acc = min(mins) if mins else base_acc
    # collapse if drops > 8pp or below baseline 56%-ish hard floor for promising
    collapses = bool(min_acc is not None and base_acc is not None and (base_acc - min_acc) >= 0.08)
    return {
        "base_accuracy": base_acc,
        "min_after_remove_1": min_acc,
        "drop_pp": (base_acc - min_acc) if base_acc is not None and min_acc is not None else None,
        "collapses": collapses,
    }


def bootstrap_accuracy(hits: Sequence[bool], n_boot: int = 200, seed: int = 20260803) -> dict[str, float | None]:
    if not hits:
        return {"low": None, "high": None, "mean": None}
    import random

    rng = random.Random(seed)
    n = len(hits)
    arr = list(hits)
    means = []
    for _ in range(n_boot):
        sample = [arr[rng.randrange(n)] for _ in range(n)]
        means.append(sum(1 for x in sample if x) / n)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[int(0.975 * n_boot)]
    return {"low": lo, "high": hi, "mean": sum(means) / len(means)}
