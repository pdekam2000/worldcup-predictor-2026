"""Backtest metrics with bootstrap intervals."""

from __future__ import annotations

import math
import random
from typing import Any, Callable, Sequence


def accuracy(y_true: Sequence[Any], y_pred: Sequence[Any]) -> float | None:
    if not y_true:
        return None
    return sum(1 for a, b in zip(y_true, y_pred) if a == b) / len(y_true)


def brier_binary(y_true: Sequence[int], p: Sequence[float]) -> float | None:
    if not y_true:
        return None
    return sum((float(pi) - float(yi)) ** 2 for yi, pi in zip(y_true, p)) / len(y_true)


def log_loss_binary(y_true: Sequence[int], p: Sequence[float], eps: float = 1e-15) -> float | None:
    if not y_true:
        return None
    s = 0.0
    for yi, pi in zip(y_true, p):
        pi = min(1 - eps, max(eps, float(pi)))
        s += -(yi * math.log(pi) + (1 - yi) * math.log(1 - pi))
    return s / len(y_true)


def multiclass_brier(y_true: Sequence[str], probs: Sequence[dict[str, float]], labels=("home", "draw", "away")) -> float | None:
    if not y_true:
        return None
    total = 0.0
    for yt, pr in zip(y_true, probs):
        for lab in labels:
            y = 1.0 if yt == lab else 0.0
            total += (float(pr.get(lab, 0.0)) - y) ** 2
    return total / len(y_true)


def multiclass_logloss(y_true: Sequence[str], probs: Sequence[dict[str, float]], labels=("home", "draw", "away"), eps=1e-15) -> float | None:
    if not y_true:
        return None
    s = 0.0
    for yt, pr in zip(y_true, probs):
        vec = [max(eps, float(pr.get(l, 0.0))) for l in labels]
        z = sum(vec)
        vec = [v / z for v in vec]
        idx = labels.index(yt) if yt in labels else 0
        s += -math.log(vec[idx])
    return s / len(y_true)


def topk_hit(actual_scores: Sequence[str], topk_lists: Sequence[Sequence[str]], k: int) -> float | None:
    if not actual_scores:
        return None
    hits = 0
    for act, tops in zip(actual_scores, topk_lists):
        if act in list(tops)[:k]:
            hits += 1
    return hits / len(actual_scores)


def bootstrap_ci(
    values: Sequence[float],
    *,
    n_boot: int = 500,
    seed: int = 42,
    alpha: float = 0.05,
) -> dict[str, float | None]:
    vals = [float(v) for v in values if v is not None]
    if len(vals) < 5:
        return {"mean": (sum(vals) / len(vals) if vals else None), "low": None, "high": None, "n": len(vals)}
    rng = random.Random(seed)
    means = []
    n = len(vals)
    for _ in range(n_boot):
        sample = [vals[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[int((1 - alpha / 2) * n_boot) - 1]
    return {"mean": sum(vals) / n, "low": lo, "high": hi, "n": n}


def paired_diff_ci(
    a: Sequence[float],
    b: Sequence[float],
    *,
    n_boot: int = 500,
    seed: int = 42,
) -> dict[str, float | None]:
    diffs = [float(x) - float(y) for x, y in zip(a, b)]
    return bootstrap_ci(diffs, n_boot=n_boot, seed=seed)
