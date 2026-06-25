"""Calibration and distribution metrics for hybrid confidence."""

from __future__ import annotations

import math
from typing import Any


def clamp01(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 4)


def probability_margin(probs: dict[str, float], *, keys: list[str] | None = None) -> float:
    vals = sorted((float(probs.get(k) or 0.0) for k in (keys or list(probs.keys()))), reverse=True)
    if len(vals) < 2:
        return float(vals[0]) if vals else 0.0
    return round(vals[0] - vals[1], 4)


def normalized_entropy(probs: dict[str, float], *, keys: list[str] | None = None) -> float:
    ks = keys or list(probs.keys())
    vals = [max(0.0, float(probs.get(k) or 0.0)) for k in ks]
    total = sum(vals)
    if total <= 0:
        return 1.0
    ent = 0.0
    for v in vals:
        p = v / total
        if p > 0:
            ent -= p * math.log(p)
    max_ent = math.log(len(ks)) if len(ks) > 1 else 1.0
    return round(ent / max_ent, 4) if max_ent > 0 else 1.0


def hazard_concentration(hazard_by_bucket: dict[str, float]) -> float:
    vals = [max(0.0, float(v)) for v in hazard_by_bucket.values()]
    total = sum(vals)
    if total <= 0:
        return 0.0
    peak = max(vals)
    return round(peak / total, 4)


def expected_calibration_error(
    confidences: list[float],
    outcomes: list[int],
    *,
    n_bins: int = 10,
) -> float | None:
    if len(confidences) < 5 or len(confidences) != len(outcomes):
        return None
    pairs = sorted(zip(confidences, outcomes), key=lambda x: x[0])
    bin_size = max(1, len(pairs) // n_bins)
    ece = 0.0
    n = len(pairs)
    for i in range(0, n, bin_size):
        chunk = pairs[i : i + bin_size]
        if not chunk:
            continue
        mean_conf = sum(c for c, _ in chunk) / len(chunk)
        mean_acc = sum(y for _, y in chunk) / len(chunk)
        ece += (len(chunk) / n) * abs(mean_conf - mean_acc)
    return round(ece, 4)


def tier_accuracy(
    tiers: list[str],
    outcomes: list[int],
    *,
    tier_order: tuple[str, ...] = ("A", "B", "C", "D"),
) -> dict[str, Any]:
    by_tier: dict[str, list[int]] = {t: [] for t in tier_order}
    for tier, hit in zip(tiers, outcomes):
        if tier in by_tier:
            by_tier[tier].append(hit)
    result: dict[str, Any] = {}
    for t in tier_order:
        hits = by_tier[t]
        result[t] = {
            "count": len(hits),
            "accuracy": round(sum(hits) / len(hits), 4) if hits else None,
        }
    return result


def is_monotonic_tiers(
    tier_stats: dict[str, Any],
    *,
    tier_order: tuple[str, ...] = ("A", "B", "C", "D"),
    min_samples: int = 1,
) -> bool:
    prev: float | None = None
    for t in tier_order:
        acc = tier_stats.get(t, {}).get("accuracy")
        count = int(tier_stats.get(t, {}).get("count") or 0)
        if acc is None or count < min_samples:
            continue
        if prev is not None and acc > prev + 1e-9:
            return False
        prev = acc
    return True
