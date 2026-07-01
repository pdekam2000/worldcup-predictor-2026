"""PHASE ECSE-X2-M5 — Market algebra shortlist scoring methods."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.research.ecse_x2_m3.equation import compute_log_home_prob_phi
from worldcup_predictor.research.ecse_x2_m2.reorder import (
    apply_reorder,
    assign_quantile,
    score_cluster,
)
from worldcup_predictor.research.ecse_x2_m4.segment import classify_match_state, odds_snapshot_valid
from worldcup_predictor.research.ecse_x2_m4.weighted_scorer import _blend_distributions
from worldcup_predictor.research.ecse_x2_m5.constants import (
    M4_WEIGHT,
    SHORTLIST_TOP_N,
    TIE_BREAK_EPSILON,
    TIE_BREAK_MIN_HOME_PROB,
)


def _top_n_rows(dist: list[dict[str, Any]], n: int = SHORTLIST_TOP_N) -> list[dict[str, Any]]:
    return [
        {
            "scoreline": r["scoreline"],
            "probability": round(float(r["probability"]), 8),
            "rank": int(r["rank"]),
        }
        for r in sorted(dist, key=lambda x: int(x["rank"]))[:n]
    ]


def _lift_weight(scoreline: str, model: dict[str, Any], quantile: int) -> float:
    score_lift = model.get("score_lift", {}).get(quantile, {})
    cluster_lift = model.get("cluster_lift", {}).get(quantile, {})
    cluster = score_cluster(scoreline)
    w = score_lift.get(scoreline, cluster_lift.get(cluster, 1.0))
    return max(0.5, min(2.0, float(w)))


def apply_shortlist_enhancer(
    baseline: list[dict[str, Any]],
    *,
    eq_val: float,
    model: dict[str, Any],
    top_n: int = SHORTLIST_TOP_N,
) -> list[dict[str, Any]]:
    pool = [dict(r) for r in sorted(baseline, key=lambda x: int(x["rank"]))[:top_n]]
    if not pool or not model.get("boundaries"):
        return _top_n_rows(baseline, top_n)

    q = assign_quantile(eq_val, model["boundaries"])
    adjusted = []
    for row in pool:
        sl = str(row["scoreline"])
        w = _lift_weight(sl, model, q)
        adjusted.append({**row, "probability": float(row["probability"]) * w})

    total = sum(float(r["probability"]) for r in adjusted)
    if total <= 0:
        return _top_n_rows(baseline, top_n)
    for row in adjusted:
        row["probability"] = round(float(row["probability"]) / total, 10)
    adjusted.sort(key=lambda r: (-float(r["probability"]), str(r["scoreline"])))
    for i, row in enumerate(adjusted, start=1):
        row["rank"] = i
    return _top_n_rows(adjusted, top_n)


def apply_tie_breaker(
    baseline: list[dict[str, Any]],
    *,
    eq_val: float,
    model: dict[str, Any],
    home_prob: float,
    top_n: int = SHORTLIST_TOP_N,
    epsilon: float = TIE_BREAK_EPSILON,
) -> list[dict[str, Any]]:
    pool = [dict(r) for r in sorted(baseline, key=lambda x: int(x["rank"]))[:top_n]]
    if (
        home_prob < TIE_BREAK_MIN_HOME_PROB
        or not pool
        or not model.get("boundaries")
        or eq_val is None
    ):
        return _top_n_rows(baseline, top_n)

    algebra = apply_reorder(baseline, value=eq_val, model=model)
    algebra_rank = {str(r["scoreline"]): int(r["rank"]) for r in algebra}

    result = sorted(pool, key=lambda r: int(r["rank"]))
    i = 0
    while i < len(result) - 1:
        gap = abs(float(result[i]["probability"]) - float(result[i + 1]["probability"]))
        if gap <= epsilon:
            j = i + 1
            while j < len(result) - 1 and abs(float(result[j]["probability"]) - float(result[j + 1]["probability"])) <= epsilon:
                j += 1
            group = result[i : j + 1]
            group.sort(key=lambda r: (algebra_rank.get(str(r["scoreline"]), 999), str(r["scoreline"])))
            result[i : j + 1] = group
            i = j + 1
        else:
            i += 1

    for idx, row in enumerate(result, start=1):
        row["rank"] = idx
    return _top_n_rows(result, top_n)


def score_all_methods(
    *,
    dist_rows: list[dict[str, Any]],
    probs: dict[str, float | None],
    lift_model: dict[str, Any] | None,
    coverage: int | None = None,
    top_n: int = SHORTLIST_TOP_N,
) -> dict[str, Any]:
    baseline = [dict(r) for r in dist_rows]
    baseline_top = _top_n_rows(baseline, top_n)
    eq_val = compute_log_home_prob_phi(probs)
    home = probs.get("ft_home")
    home_prob = round(float(home), 6) if home is not None and math.isfinite(home) else None
    odds_ok = odds_snapshot_valid(probs, coverage)
    algebra_ready = eq_val is not None and lift_model is not None and odds_ok

    outputs: dict[str, list[dict[str, Any]]] = {"champion": baseline_top}

    state = classify_match_state(probs)
    is_balanced = state == "balanced"

    if algebra_ready:
        m3_full = apply_reorder(baseline, value=eq_val, model=lift_model)
        outputs["m3_full_reorder"] = _top_n_rows(m3_full, top_n)
        blended = _blend_distributions(baseline, m3_full, M4_WEIGHT)
        outputs["m4_weight_005"] = _top_n_rows(blended, top_n)
        if not is_balanced:
            outputs["shortlist_enhancer"] = apply_shortlist_enhancer(
                baseline, eq_val=eq_val, model=lift_model, top_n=top_n
            )
        else:
            outputs["shortlist_enhancer"] = baseline_top
        outputs["tie_breaker"] = apply_tie_breaker(
            baseline,
            eq_val=eq_val,
            model=lift_model,
            home_prob=float(home_prob or 0),
            top_n=top_n,
        )
    else:
        for key in ("m3_full_reorder", "m4_weight_005", "shortlist_enhancer", "tie_breaker"):
            outputs[key] = baseline_top

    return {
        "home_prob": home_prob,
        "equation_value": round(eq_val, 8) if eq_val is not None else None,
        "algebra_ready": algebra_ready,
        "match_state": classify_match_state(probs),
        "outputs": outputs,
    }
