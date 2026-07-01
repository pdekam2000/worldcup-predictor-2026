"""PHASE ECSE-X2-M4 — Weight rejection and promotion recommendation."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_x2_m4.constants import (
    MAX_LOG_LOSS_WORSEN,
    MAX_RANK_VOLATILITY,
    MIN_FOLDS_IMPROVED_TOP3,
    MIN_SEGMENT_SAMPLE,
)


def assess_weight(
    weight: float,
    *,
    metrics: dict[str, Any],
    fold_deltas: list[dict[str, Any]],
    mid_bucket_delta: dict[str, Any],
    leak_count: int,
    balanced_affected: int,
) -> dict[str, Any]:
    reasons: list[str] = []
    delta = metrics.get("delta") or {}
    n = int(metrics.get("n") or 0)

    if n < MIN_SEGMENT_SAMPLE:
        reasons.append("sample_too_small")

    if float(delta.get("avg_log_loss", 0)) > MAX_LOG_LOSS_WORSEN:
        reasons.append("log_loss_worsens_materially")

    volatility = float(metrics.get("volatility_score") or 0)
    if volatility > MAX_RANK_VOLATILITY:
        reasons.append("excessive_rank_movement")

    folds_top3_pos = sum(1 for f in fold_deltas if float(f.get("top3_delta_pp", 0)) > 0)
    if fold_deltas and folds_top3_pos < MIN_FOLDS_IMPROVED_TOP3:
        reasons.append("gain_only_some_folds")

    mid_n = int(mid_bucket_delta.get("n") or 0)
    if mid_n >= 200 and float(mid_bucket_delta.get("top3_delta_pp", 0)) < -0.3:
        reasons.append("bad_mid_home_prob_bucket")

    if leak_count > 0:
        reasons.append("leaked_without_odds")

    if balanced_affected > 0:
        reasons.append("balanced_match_leak")

    top1_up = float(delta.get("top1_delta_pp", 0)) > 0.05
    top3_down = float(delta.get("top3_delta_pp", 0)) < 0
    if top1_up and top3_down:
        reasons.append("top1_only_gain")

    accepted = not any(
        r
        in {
            "log_loss_worsens_materially",
            "excessive_rank_movement",
            "leaked_without_odds",
            "balanced_match_leak",
            "top1_only_gain",
        }
        for r in reasons
    )

    return {
        "weight": weight,
        "accepted": accepted,
        "reasons": reasons,
        "folds_top3_positive": folds_top3_pos,
    }


def recommend_best_weight(
    weight_results: list[dict[str, Any]],
    *,
    segment_coverage_rate: float,
) -> dict[str, Any]:
    accepted = [w for w in weight_results if (w.get("assessment") or {}).get("accepted")]
    if not accepted:
        rec = _fallback_recommendation(weight_results, segment_coverage_rate)
        return {"best_weight": None, "recommendation": rec, "accepted_weights": []}

    def score_row(w: dict[str, Any]) -> tuple[float, float, float]:
        d = (w.get("metrics") or {}).get("delta") or {}
        return (
            float(d.get("top3_delta_pp", 0)),
            -float(d.get("avg_log_loss", 0)),
            -float(w.get("metrics", {}).get("volatility_score") or 0),
        )

    best = max(accepted, key=score_row)
    best_weight = best["weight"]
    d = (best.get("metrics") or {}).get("delta") or {}

    if "balanced_match_leak" in (best.get("reasons") or []):
        return {
            "best_weight": best_weight,
            "recommendation": "REJECT_BALANCED_MATCH_RISK",
            "accepted_weights": [w["weight"] for w in accepted],
        }

    if segment_coverage_rate < 0.25:
        return {
            "best_weight": best_weight,
            "recommendation": "NEED_MORE_ODDS_COVERAGE",
            "accepted_weights": [w["weight"] for w in accepted],
        }

    if float(d.get("top3_delta_pp", 0)) >= 0.3 and float(d.get("avg_log_loss", 0)) <= 0:
        return {
            "best_weight": best_weight,
            "recommendation": "PROMOTE_SMALL_WEIGHT_SHADOW_LIVE",
            "accepted_weights": [w["weight"] for w in accepted],
        }

    return {
        "best_weight": best_weight,
        "recommendation": "KEEP_RESEARCH_ONLY",
        "accepted_weights": [w["weight"] for w in accepted],
    }


def _fallback_recommendation(weight_results: list[dict[str, Any]], coverage: float) -> str:
    reasons = {r for w in weight_results for r in (w.get("reasons") or [])}
    if "balanced_match_leak" in reasons:
        return "REJECT_BALANCED_MATCH_RISK"
    if coverage < 0.25:
        return "NEED_MORE_ODDS_COVERAGE"
    return "KEEP_RESEARCH_ONLY"
