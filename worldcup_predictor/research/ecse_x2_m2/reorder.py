"""PHASE ECSE-X2-M2 — Reorder rules from quantile lift tables."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from worldcup_predictor.research.ecse_score_distribution import PROB_SUM_TOLERANCE
from worldcup_predictor.research.ecse_x2_m2.constants import NUM_QUANTILES, REORDER_POWER, SCORE_CLUSTERS


def assign_quantile(value: float, boundaries: list[float]) -> int:
    for i, bound in enumerate(boundaries[1:], start=1):
        if value <= bound:
            return i - 1
    return len(boundaries) - 2


def quantile_boundaries(values: list[float], *, n: int = NUM_QUANTILES) -> list[float]:
    if not values:
        return [0.0, 1.0]
    sorted_vals = sorted(values)
    bounds = [sorted_vals[0]]
    for i in range(1, n):
        idx = min(len(sorted_vals) - 1, int(len(sorted_vals) * i / n))
        bounds.append(sorted_vals[idx])
    bounds.append(sorted_vals[-1])
    return bounds


def learn_lift_table(
    train_rows: list[dict[str, Any]],
    *,
    n_quantiles: int = NUM_QUANTILES,
) -> dict[str, Any]:
    """
    Learn per-quantile scoreline lift vs global train frequency.
  train_rows items: {value, actual, actual_cluster}
    """
    values = [float(r["value"]) for r in train_rows]
    boundaries = quantile_boundaries(values, n=n_quantiles)
    global_counts: Counter[str] = Counter(r["actual"] for r in train_rows)
    global_n = len(train_rows)
    global_cluster: Counter[str] = Counter(r["actual_cluster"] for r in train_rows)

    bin_rows: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in train_rows:
        q = assign_quantile(float(row["value"]), boundaries)
        bin_rows[q].append(row)

    score_lift: dict[int, dict[str, float]] = {}
    cluster_lift: dict[int, dict[str, float]] = {}

    for q, rows in bin_rows.items():
        n = len(rows)
        if n < 30:
            continue
        local = Counter(r["actual"] for r in rows)
        local_cluster = Counter(r["actual_cluster"] for r in rows)
        score_lift[q] = {}
        for score, c in local.items():
            g = global_counts[score] / global_n
            if g <= 0:
                continue
            lift = (c / n) / g
            score_lift[q][score] = max(0.55, min(1.85, lift))
        cluster_lift[q] = {}
        for cluster, c in local_cluster.items():
            g = global_cluster[cluster] / global_n
            if g <= 0:
                continue
            lift = (c / n) / g
            cluster_lift[q][cluster] = max(0.60, min(1.75, lift))

    return {
        "boundaries": boundaries,
        "score_lift": score_lift,
        "cluster_lift": cluster_lift,
        "train_n": len(train_rows),
    }


def score_cluster(scoreline: str) -> str:
    for name, members in SCORE_CLUSTERS.items():
        if scoreline in members:
            return name
    h, a = _parse_score(scoreline)
    if h is None:
        return "other"
    total = h + a
    if total <= 1:
        return "low_total"
    if total >= 4:
        return "high_scoring"
    if h > a:
        return "home_win"
    if a > h:
        return "away_win"
    return "drawish"


def _parse_score(scoreline: str) -> tuple[int | None, int | None]:
    if "-" not in scoreline:
        return None, None
    try:
        h, a = scoreline.split("-", 1)
        return int(h), int(a)
    except ValueError:
        return None, None


def apply_reorder(
    dist_rows: list[dict[str, Any]],
    *,
    value: float,
    model: dict[str, Any],
    power: float = REORDER_POWER,
) -> list[dict[str, Any]]:
    if not dist_rows or not model.get("boundaries"):
        return [dict(r) for r in dist_rows]

    q = assign_quantile(value, model["boundaries"])
    score_lift = model.get("score_lift", {}).get(q, {})
    cluster_lift = model.get("cluster_lift", {}).get(q, {})

    weighted: list[dict[str, Any]] = []
    for row in dist_rows:
        sl = str(row["scoreline"])
        cluster = score_cluster(sl)
        w = score_lift.get(sl, cluster_lift.get(cluster, 1.0))
        w = max(0.5, min(2.0, float(w)))
        weighted.append({**row, "probability": float(row["probability"]) * (w**power)})

    total = sum(r["probability"] for r in weighted)
    if total <= 0:
        return [dict(r) for r in dist_rows]
    for row in weighted:
        row["probability"] = round(row["probability"] / total, 10)
    weighted.sort(key=lambda r: (-float(r["probability"]), str(r["scoreline"])))
    for i, row in enumerate(weighted, start=1):
        row["rank"] = i

    prob_sum = sum(float(r["probability"]) for r in weighted)
    if abs(prob_sum - 1.0) > PROB_SUM_TOLERANCE:
        total = prob_sum
        for row in weighted:
            row["probability"] = round(float(row["probability"]) / total, 10)
    return weighted
