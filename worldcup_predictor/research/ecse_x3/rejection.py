"""PHASE ECSE-X3-A — Challenger rejection and recommendation."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_x3.constants import (
    MAX_LOG_LOSS_WORSEN,
    MAX_TOP3_WORSEN,
    MIN_ELIGIBLE_SAMPLE,
    MIN_FOLDS_IMPROVED,
    PROMOTE_TOP1_MIN,
    PROMOTE_TOP3_MIN,
    PROMOTE_TOP5_MIN,
    RECOMMENDATIONS,
)


def assess_method(
    method: str,
    *,
    delta: dict[str, float],
    fold_deltas: list[dict[str, Any]],
    balanced_delta: dict[str, float],
    metrics_n: int,
    nan_inf: bool = False,
) -> dict[str, Any]:
    reasons: list[str] = []
    if method == "champion":
        return {"method": method, "accepted": True, "reasons": [], "folds_positive_top1": 0}

    if nan_inf:
        reasons.append("nan_inf")

    if metrics_n < MIN_ELIGIBLE_SAMPLE:
        reasons.append("sample_too_small")

    if float(delta.get("top3_delta_pp", 0)) < -MAX_TOP3_WORSEN:
        reasons.append("top3_worsens_materially")

    top5_up = float(delta.get("top5_delta_pp", 0)) > 0.5
    top1_down = float(delta.get("top1_delta_pp", 0)) < -0.5
    if top5_up and top1_down:
        reasons.append("top5_up_top1_collapses")

    if float(delta.get("avg_log_loss", 0)) > MAX_LOG_LOSS_WORSEN:
        reasons.append("log_loss_worsens")

    folds_top1_pos = sum(1 for f in fold_deltas if float(f.get("top1_delta_pp", 0)) > 0)
    if fold_deltas and folds_top1_pos < MIN_FOLDS_IMPROVED:
        reasons.append("gain_only_one_fold")

    if int(balanced_delta.get("n", 0)) >= 200 and float(balanced_delta.get("top3_delta_pp", 0)) < -0.5:
        reasons.append("balanced_degrades")

    hard = {
        "nan_inf",
        "top3_worsens_materially",
        "top5_up_top1_collapses",
        "log_loss_worsens",
        "balanced_degrades",
        "gain_only_one_fold",
    }
    return {
        "method": method,
        "accepted": not (hard & set(reasons)),
        "reasons": reasons,
        "folds_positive_top1": folds_top1_pos,
    }


def recommend(
    method_results: dict[str, dict[str, Any]],
    *,
    eligible_n: int,
    coverage_rate: float,
    missing_odds_rate: float,
) -> dict[str, Any]:
    if eligible_n < MIN_ELIGIBLE_SAMPLE or coverage_rate < 0.25:
        return {"best_method": None, "recommendation": "NEED_MORE_ODDS_COVERAGE"}

    if missing_odds_rate > 0.65:
        return {"best_method": None, "recommendation": "NEED_MORE_ODDS_COVERAGE"}

    candidates: list[tuple[str, dict[str, float], dict[str, Any]]] = []
    for method, data in method_results.items():
        if method == "champion":
            continue
        assessment = data.get("assessment") or {}
        if not assessment.get("accepted"):
            continue
        delta = (data.get("overall") or {}).get("delta") or {}
        candidates.append((method, delta, assessment))

    if not candidates:
        return {"best_method": None, "recommendation": "REJECT_COMPOSITE"}

    def score(c: tuple[str, dict, dict]) -> tuple[float, float, float, float]:
        _, delta, _ = c
        return (
            float(delta.get("top1_delta_pp", 0)),
            float(delta.get("top3_delta_pp", 0)),
            float(delta.get("top5_delta_pp", 0)),
            -float(delta.get("avg_log_loss", 0)),
        )

    best_method, best_delta, _ = max(candidates, key=score)

    t1 = float(best_delta.get("top1_delta_pp", 0))
    t3 = float(best_delta.get("top3_delta_pp", 0))
    t5 = float(best_delta.get("top5_delta_pp", 0))
    ll = float(best_delta.get("avg_log_loss", 0))

    folds_ok = (method_results.get(best_method) or {}).get("assessment", {}).get("folds_positive_top1", 0) >= MIN_FOLDS_IMPROVED

    if t1 >= PROMOTE_TOP1_MIN and t3 >= PROMOTE_TOP3_MIN and t5 >= PROMOTE_TOP5_MIN and ll <= 0 and folds_ok:
        return {"best_method": best_method, "recommendation": "PROMOTE_COMPOSITE_TO_OWNER_LAB"}

    if best_method == "zz2_only" and t1 >= 0.5:
        return {"best_method": best_method, "recommendation": "USE_ONLY_ZZ2_DETECTOR"}

    if best_method in ("hi_only", "j2_g_slope") and t1 >= 0.3:
        return {"best_method": best_method, "recommendation": "USE_ONLY_HI_J2_G_SLOPE"}

    if t5 > 0 or t1 > 0:
        return {"best_method": best_method, "recommendation": "KEEP_SHADOW_MORE_DATA"}

    return {"best_method": best_method, "recommendation": "REJECT_COMPOSITE"}
