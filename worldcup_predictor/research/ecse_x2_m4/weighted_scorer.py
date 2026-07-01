"""PHASE ECSE-X2-M4 — Weighted internal adjustment scorer."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_x2_m3.equation import compute_log_home_prob_phi
from worldcup_predictor.research.ecse_x2_m3.scorer import build_lift_model
from worldcup_predictor.research.ecse_x2_m4.segment import evaluate_target_segment
from worldcup_predictor.research.ecse_x2_m2.reorder import apply_reorder


def _top_n(dist: list[dict[str, Any]], n: int = 10) -> list[dict[str, Any]]:
    return [
        {
            "scoreline": r["scoreline"],
            "probability": round(float(r["probability"]), 8),
            "rank": int(r["rank"]),
        }
        for r in sorted(dist, key=lambda x: int(x["rank"]))[:n]
    ]


def _blend_distributions(
    baseline: list[dict[str, Any]],
    adjusted: list[dict[str, Any]],
    weight: float,
) -> list[dict[str, Any]]:
    base_map = {str(r["scoreline"]): float(r["probability"]) for r in baseline}
    adj_map = {str(r["scoreline"]): float(r["probability"]) for r in adjusted}
    scorelines = sorted(set(base_map) | set(adj_map))
    blended: list[dict[str, Any]] = []
    for sl in scorelines:
        p0 = base_map.get(sl, 0.0)
        p1 = adj_map.get(sl, p0)
        blended.append({"scoreline": sl, "probability": (1.0 - weight) * p0 + weight * p1})
    total = sum(r["probability"] for r in blended)
    if total <= 0:
        return [dict(r) for r in baseline]
    for row in blended:
        row["probability"] = round(row["probability"] / total, 10)
    blended.sort(key=lambda r: (-float(r["probability"]), str(r["scoreline"])))
    for i, row in enumerate(blended, start=1):
        row["rank"] = i
        row["home_goals"] = next(
            (r.get("home_goals") for r in baseline if str(r["scoreline"]) == row["scoreline"]),
            None,
        )
        row["away_goals"] = next(
            (r.get("away_goals") for r in baseline if str(r["scoreline"]) == row["scoreline"]),
            None,
        )
    return blended


def score_fixture_weighted(
    *,
    dist_rows: list[dict[str, Any]],
    probs: dict[str, float | None],
    lift_model: dict[str, Any] | None,
    weight: float,
    coverage: int | None = None,
    top_n: int = 10,
) -> dict[str, Any]:
    baseline = [dict(r) for r in dist_rows]
    baseline_top = _top_n(baseline, top_n)
    segment = evaluate_target_segment(probs, coverage=coverage)
    eq_val = compute_log_home_prob_phi(probs)

    if not segment["target_segment_passed"] or eq_val is None or lift_model is None:
        return {
            "applied": False,
            "target_segment_passed": segment["target_segment_passed"],
            "exclusion_reason": segment.get("exclusion_reason"),
            "home_prob": segment.get("home_prob"),
            "equation_value": round(eq_val, 8) if eq_val is not None else None,
            "applied_weight": None,
            "baseline_top": baseline_top,
            "weighted_top": baseline_top,
            "top1_disagreement": False,
            "rank_movements": {},
        }

    full_adjusted = apply_reorder(baseline, value=eq_val, model=lift_model)
    weighted = _blend_distributions(baseline, full_adjusted, weight)
    weighted_top = _top_n(weighted, top_n)

    base_rank = {r["scoreline"]: r["rank"] for r in baseline_top}
    w_rank = {r["scoreline"]: r["rank"] for r in weighted_top}
    rank_movements = {
        sl: int(base_rank[sl]) - int(w_rank[sl])
        for sl in set(base_rank) & set(w_rank)
        if base_rank[sl] != w_rank[sl]
    }

    base_top1 = baseline_top[0]["scoreline"] if baseline_top else None
    w_top1 = weighted_top[0]["scoreline"] if weighted_top else None

    return {
        "applied": True,
        "target_segment_passed": True,
        "exclusion_reason": None,
        "home_prob": segment["home_prob"],
        "equation_value": round(eq_val, 8),
        "applied_weight": weight,
        "baseline_top": baseline_top,
        "weighted_top": weighted_top,
        "top1_disagreement": base_top1 != w_top1,
        "rank_movements": rank_movements,
    }


def build_segment_lift_model(train_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    segment_rows = []
    for row in train_rows:
        seg = evaluate_target_segment(row["probs"], coverage=row.get("feature_coverage_count"))
        if not seg["target_segment_passed"]:
            continue
        val = compute_log_home_prob_phi(row["probs"])
        if val is None:
            continue
        segment_rows.append(row)
    return build_lift_model(segment_rows)
