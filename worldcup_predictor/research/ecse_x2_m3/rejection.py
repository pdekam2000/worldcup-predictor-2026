"""PHASE ECSE-X2-M3 — Overfit rejection and promotion recommendation."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_x2_m3.constants import (
    MAX_LOG_LOSS_WORSEN,
    MAX_RANK_VOLATILITY,
    MIN_ELIGIBLE_SAMPLE,
    MIN_FOLDS_IMPROVED_TOP3,
    MIN_FOLD_SAMPLE,
)


def assess_overfit_risk(summary: dict[str, Any]) -> dict[str, Any]:
    fold_deltas = summary.get("fold_deltas") or []
    reasons: list[str] = []

    if int(summary.get("eligible_n") or 0) < MIN_ELIGIBLE_SAMPLE:
        reasons.append("sample_too_small")

    folds_top3_pos = sum(1 for f in fold_deltas if float(f.get("top3_delta_pp", 0)) > 0)
    folds_top1_pos = sum(1 for f in fold_deltas if float(f.get("top1_delta_pp", 0)) > 0)
    if fold_deltas and folds_top3_pos < MIN_FOLDS_IMPROVED_TOP3:
        reasons.append("gain_only_some_folds")

    overall = summary.get("overall_delta") or {}
    if float(overall.get("avg_log_loss", 0)) > MAX_LOG_LOSS_WORSEN:
        reasons.append("log_loss_worsens_materially")
    if float(overall.get("top1_delta_pp", 0)) > 0 and float(overall.get("avg_log_loss", 0)) > 0:
        reasons.append("top1_up_logloss_worse")

    balanced = summary.get("balanced_match_delta") or {}
    if balanced.get("n", 0) >= MIN_FOLD_SAMPLE and float(balanced.get("top3_delta_pp", 0)) < -0.5:
        reasons.append("collapses_on_balanced_fixtures")

    volatility = float(summary.get("avg_rank_movement", 0))
    if volatility > MAX_RANK_VOLATILITY:
        reasons.append("excessive_rank_volatility")

    unrealistic = summary.get("unrealistic_score_push") or {}
    if unrealistic.get("flag"):
        reasons.append("unrealistic_high_score_push")

    missing_odds_rate = float(summary.get("missing_odds_rate") or 0)
    if missing_odds_rate > 0.45:
        reasons.append("partial_odds_coverage")
    if missing_odds_rate > 0.45 and int(summary.get("eligible_n") or 0) < MIN_ELIGIBLE_SAMPLE:
        reasons.append("unstable_odds_coverage")

    for f in fold_deltas:
        if int(f.get("n", 0)) < MIN_FOLD_SAMPLE:
            reasons.append("fold_sample_too_small")
            break

    recommendation = _recommend(reasons, overall, folds_top3_pos, len(fold_deltas))
    if recommendation == "PROMOTE_TO_INTERNAL_WEIGHT_TEST" and "partial_odds_coverage" in reasons:
        recommendation = "KEEP_SHADOW_MORE_DATA"
    return {
        "reasons": reasons,
        "folds_top3_positive": folds_top3_pos,
        "folds_top1_positive": folds_top1_pos,
        "recommendation": recommendation,
        "promotion_ready": recommendation == "PROMOTE_TO_INTERNAL_WEIGHT_TEST",
    }


def _recommend(
    reasons: list[str],
    overall: dict[str, float],
    folds_top3_pos: int,
    fold_count: int,
) -> str:
    hard_reject = {
        "log_loss_worsens_materially",
        "collapses_on_balanced_fixtures",
        "excessive_rank_volatility",
        "unrealistic_high_score_push",
    }
    if hard_reject & set(reasons):
        return "REJECT_OVERFIT"
    if "unstable_odds_coverage" in reasons or "sample_too_small" in reasons:
        return "NEED_MORE_ODDS_COVERAGE"
    if "gain_only_some_folds" in reasons and folds_top3_pos < max(2, fold_count // 2):
        return "KEEP_SHADOW_MORE_DATA"
    if (
        float(overall.get("top3_delta_pp", 0)) >= 0.5
        and float(overall.get("avg_log_loss", 0)) <= 0
        and folds_top3_pos >= MIN_FOLDS_IMPROVED_TOP3
    ):
        return "PROMOTE_TO_INTERNAL_WEIGHT_TEST"
    if float(overall.get("top3_delta_pp", 0)) > 0:
        return "KEEP_SHADOW_MORE_DATA"
    return "REJECT_OVERFIT"
