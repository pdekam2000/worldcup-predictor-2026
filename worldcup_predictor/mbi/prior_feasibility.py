"""Part E — historical prior feasibility at 1%, 5%, 10% blend weights."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from worldcup_predictor.mbi.models import PRIOR_WEIGHTS


def _brier(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None
    return round(sum((p - y) ** 2 for p, y in pairs) / len(pairs), 4)


def simulate_prior_blend(
    selections: list[Any],
    bucket_table: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Blend bookmaker implied probability with bucket historical hit rate.
    Uses match_winner and over_under where outcomes are available.
    """
    bucket_lookup: dict[tuple[str, str, str], float] = {}
    bucket_n: dict[tuple[str, str, str], int] = {}
    for row in bucket_table:
        key = (row["market_key"], row["bucket"], row["selection"])
        bucket_lookup[key] = float(row["hit_rate"])
        bucket_n[key] = int(row["count"])

    # Deduplicate: one row per fixture/market/selection (median odds across books)
    fixture_rows: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    for r in selections:
        if r.hit is None or r.market_key not in ("match_winner", "over_under", "first_team_to_score"):
            continue
        fixture_rows[(r.fixture_key, r.market_key, r.selection)].append(r)

    results: dict[str, Any] = {"by_weight": {}, "baseline_brier": None, "best_weight": 0.0, "best_brier": None}
    baseline_pairs: list[tuple[float, int]] = []

    for weight in PRIOR_WEIGHTS:
        pairs: list[tuple[float, int]] = []
        for key, rows in fixture_rows.items():
            fixture_key, market_key, selection = key
            implied_vals = [r.implied_probability for r in rows if r.implied_probability]
            if not implied_vals:
                continue
            implied = sum(implied_vals) / len(implied_vals)
            bucket = rows[0].bucket
            if not bucket:
                continue
            bkey = (market_key, bucket, selection)
            prior = bucket_lookup.get(bkey)
            if prior is None or bucket_n.get(bkey, 0) < 30:
                blended = implied
            else:
                blended = (1 - weight) * implied + weight * prior
            blended = max(0.01, min(0.99, blended))
            y = 1 if rows[0].hit else 0
            pairs.append((blended, y))
            if weight == 0.0:
                baseline_pairs.append((implied, y))

        brier = _brier(pairs)
        results["by_weight"][str(weight)] = {"brier": brier, "n": len(pairs)}
        if weight == 0.0:
            results["baseline_brier"] = brier

    best_w = 0.0
    best_b = results["baseline_brier"]
    for w_str, metrics in results["by_weight"].items():
        b = metrics.get("brier")
        if b is not None and (best_b is None or b < best_b):
            best_b = b
            best_w = float(w_str)
    results["best_weight"] = best_w
    results["best_brier"] = best_b
    results["improvement"] = (
        round(results["baseline_brier"] - best_b, 4)
        if results["baseline_brier"] is not None and best_b is not None
        else None
    )
    results["feasible"] = bool(results.get("improvement") and results["improvement"] > 0.001)
    return results


def decide_prior_recommendation(prior_results: dict[str, Any], edge_results: dict[str, Any]) -> dict[str, Any]:
    strong = int(edge_results.get("strong_bias_count") or 0)
    bias = int(edge_results.get("bias_count") or 0)
    improvement = float(prior_results.get("improvement") or 0)
    feasible = bool(prior_results.get("feasible"))

    if feasible and strong >= 3 and improvement >= 0.005:
        rec = "MBI_HIGH_VALUE"
        rationale = "Prior blend improves Brier with multiple strong bucket biases"
    elif (bias >= 5 or feasible) and improvement >= 0.001:
        rec = "MBI_MEDIUM_VALUE"
        rationale = "Detectable calibration gaps; modest prior lift at low blend weights"
    else:
        rec = "MBI_NO_VALUE"
        rationale = "Insufficient persistent bias or prior blend does not improve calibration"

    return {
        "recommendation": rec,
        "rationale": rationale,
        "strong_biases": strong,
        "persistent_biases": bias,
        "prior_improvement": improvement,
        "best_prior_weight": prior_results.get("best_weight"),
    }
