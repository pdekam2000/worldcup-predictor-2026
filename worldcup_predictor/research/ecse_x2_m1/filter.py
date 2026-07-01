"""PHASE ECSE-X2-M1 — Re-rank ECSE scorelines using BTTS×OU quadrant weights."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_score_distribution import OTHER_SCORELINE, PROB_SUM_TOLERANCE
from worldcup_predictor.research.ecse_x2_m1.quadrants import scoreline_quadrant_compat

COMPAT_POWER = 1.15
WEIGHT_FLOOR = 0.05


def apply_m1_quadrant_filter(
    baseline_rows: list[dict[str, Any]],
    market: dict[str, Any],
    *,
    compat_power: float = COMPAT_POWER,
) -> list[dict[str, Any]]:
    """
    Re-weight baseline probabilities by quadrant compatibility, then re-rank.
    Does not use actual match results.
    """
    if not baseline_rows:
        return []
    if not market.get("ok"):
        return [dict(r) for r in baseline_rows]

    q_probs = market["quadrant_probs"]
    weighted: list[dict[str, Any]] = []
    for row in baseline_rows:
        base_p = float(row["probability"])
        compat = scoreline_quadrant_compat(
            int(row["home_goals"]),
            int(row["away_goals"]),
            str(row["scoreline"]),
            q_probs,
        )
        weight = max(WEIGHT_FLOOR, compat**compat_power)
        weighted.append(
            {
                **row,
                "baseline_probability": base_p,
                "quadrant_compat": round(compat, 8),
                "m1_weight": round(weight, 8),
                "probability": base_p * weight,
            }
        )

    total = sum(r["probability"] for r in weighted)
    if total <= 0:
        return [dict(r) for r in baseline_rows]

    for row in weighted:
        row["probability"] = round(float(row["probability"]) / total, 10)

    prob_sum = sum(r["probability"] for r in weighted)
    if abs(prob_sum - 1.0) > PROB_SUM_TOLERANCE:
        weighted = _renormalize(weighted)

    weighted.sort(key=lambda r: (-float(r["probability"]), str(r["scoreline"])))
    for idx, row in enumerate(weighted, start=1):
        row["rank"] = idx
    return weighted


def _renormalize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = sum(float(r["probability"]) for r in rows)
    if total <= 0:
        return rows
    for row in rows:
        row["probability"] = round(float(row["probability"]) / total, 10)
    return rows
