"""PHASE ECSE-X2-M5 — Method rejection rules and final recommendation."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_x2_m5.constants import (
    MAX_LOG_LOSS_WORSEN,
    MAX_RANK_VOLATILITY,
    MAX_TOP3_WORSEN,
    MIN_ELIGIBLE_SAMPLE,
    MIN_FOLDS_IMPROVED_TOP5,
)


def assess_method(
    method: str,
    *,
    delta: dict[str, float],
    fold_deltas: list[dict[str, Any]],
    balanced_delta: dict[str, float],
    volatility: float,
    leak_count: int,
    metrics_n: int,
) -> dict[str, Any]:
    reasons: list[str] = []

    if metrics_n < MIN_ELIGIBLE_SAMPLE and method != "champion":
        reasons.append("sample_too_small")

    if float(delta.get("top3_delta_pp", 0)) < -MAX_TOP3_WORSEN:
        reasons.append("top3_worsens_materially")

    if float(delta.get("avg_log_loss", 0)) > MAX_LOG_LOSS_WORSEN:
        reasons.append("log_loss_worsens")

    folds_top5_pos = sum(1 for f in fold_deltas if float(f.get("top5_delta_pp", 0)) > 0)
    if fold_deltas and folds_top5_pos < MIN_FOLDS_IMPROVED_TOP5:
        reasons.append("gain_only_one_fold")

    if int(balanced_delta.get("n", 0)) >= 200 and float(balanced_delta.get("top5_delta_pp", 0)) < -0.3:
        reasons.append("balanced_degrades")

    if volatility > MAX_RANK_VOLATILITY:
        reasons.append("high_rank_volatility")

    if leak_count > 0:
        reasons.append("missing_odds_leak")

    top5_up = float(delta.get("top5_delta_pp", 0)) > 0.1
    rank_worse = float(delta.get("avg_actual_rank", 0)) > 0.05
    if top5_up and rank_worse:
        reasons.append("top5_up_avg_rank_worse")

    top1_up = float(delta.get("top1_delta_pp", 0)) > 0.05
    top3_down = float(delta.get("top3_delta_pp", 0)) < 0
    if top1_up and top3_down:
        reasons.append("top1_only_gain")

    hard = {
        "top3_worsens_materially",
        "balanced_degrades",
        "high_rank_volatility",
        "missing_odds_leak",
        "top5_up_avg_rank_worse",
    }
    accepted = method == "champion" or not (hard & set(reasons))

    return {
        "method": method,
        "accepted": accepted,
        "reasons": reasons,
        "folds_top5_positive": folds_top5_pos,
    }


def recommend(
    method_results: dict[str, dict[str, Any]],
    *,
    eligible_n: int,
    coverage_rate: float,
) -> dict[str, Any]:
    if eligible_n < MIN_ELIGIBLE_SAMPLE or coverage_rate < 0.25:
        return {
            "best_method": None,
            "recommendation": "NEED_MORE_ODDS_COVERAGE",
        }

    candidates = []
    for method, data in method_results.items():
        if method == "champion":
            continue
        assessment = data.get("assessment") or {}
        if not assessment.get("accepted"):
            continue
        delta = (data.get("overall") or {}).get("delta") or {}
        candidates.append((method, delta, assessment))

    if not candidates:
        reasons = {r for m, d in method_results.items() for r in (d.get("assessment") or {}).get("reasons", [])}
        if "balanced_degrades" in reasons:
            return {"best_method": None, "recommendation": "REJECT_NO_SHORTLIST_VALUE"}
        return {"best_method": None, "recommendation": "KEEP_RESEARCH_ONLY"}

    def score(c: tuple[str, dict, dict]) -> tuple[float, float, float]:
        _, delta, _ = c
        return (
            float(delta.get("top5_delta_pp", 0)),
            float(delta.get("top3_delta_pp", 0)),
            -float(delta.get("avg_log_loss", 0)),
        )

    best_method, best_delta, best_assessment = max(candidates, key=score)

    if float(best_delta.get("top5_delta_pp", 0)) < 0.05:
        return {"best_method": best_method, "recommendation": "REJECT_NO_SHORTLIST_VALUE"}

    if "balanced_degrades" in (best_assessment.get("reasons") or []):
        return {"best_method": best_method, "recommendation": "REJECT_NO_SHORTLIST_VALUE"}

    if (
        float(best_delta.get("top5_delta_pp", 0)) >= 0.5
        and float(best_delta.get("top3_delta_pp", 0)) >= -0.05
        and float(best_delta.get("avg_log_loss", 0)) <= 0
    ):
        return {"best_method": best_method, "recommendation": "PROMOTE_SHORTLIST_SHADOW_LIVE"}

    if float(best_delta.get("top5_delta_pp", 0)) >= 0.15:
        return {"best_method": best_method, "recommendation": "USE_AS_ADMIN_ONLY_SIGNAL"}

    return {"best_method": best_method, "recommendation": "KEEP_RESEARCH_ONLY"}
