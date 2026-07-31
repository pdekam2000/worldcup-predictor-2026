"""Chronological evaluation + policy comparison — research-only."""

from __future__ import annotations

import copy
from typing import Any

import numpy as np

from worldcup_predictor.research.betting_day_similarity.clustering import (
    choose_kmeans_k,
    describe_regime,
    fit_regimes,
    predict_regime,
)
from worldcup_predictor.research.betting_day_similarity.distance_metrics import stable_inv_cov
from worldcup_predictor.research.betting_day_similarity.nearest_neighbors import format_analogs, knn_indices
from worldcup_predictor.research.betting_day_similarity.ood_detection import ood_status
from worldcup_predictor.research.betting_day_similarity.overlay_policy import apply_similarity_overlay
from worldcup_predictor.research.betting_day_similarity.preprocessing import FeatureScaler, matrix_from_days
from worldcup_predictor.research.betting_day_similarity.similarity_score import day_similarity_quality_score


def chronological_splits(days: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(days)
    i60 = int(n * 0.60)
    i80 = int(n * 0.80)
    train, val, hold = days[:i60], days[i60:i80], days[i80:]
    return {
        "train": train,
        "validation": val,
        "holdout": hold,
        "manifest": {
            "train_n": len(train),
            "validation_n": len(val),
            "holdout_n": len(hold),
            "train_dates": [train[0]["vienna_date"], train[-1]["vienna_date"]] if train else [],
            "validation_dates": [val[0]["vienna_date"], val[-1]["vienna_date"]] if val else [],
            "holdout_dates": [hold[0]["vienna_date"], hold[-1]["vienna_date"]] if hold else [],
            "shuffle": False,
            "overlap_train_val": bool({d["vienna_date"] for d in train} & {d["vienna_date"] for d in val}),
            "overlap_val_hold": bool({d["vienna_date"] for d in val} & {d["vienna_date"] for d in hold}),
        },
    }


def _summarize_pnl(days_eval: list[dict[str, Any]], exposure_key: str, pnl_key: str) -> dict[str, Any]:
    n = len(days_eval) or 1
    staked = sum(float(d.get(exposure_key) or 0) for d in days_eval)
    pnl = sum(float(d.get(pnl_key) or 0) for d in days_eval)
    active = [d for d in days_eval if float(d.get(exposure_key) or 0) > 0]
    eq = peak = dd = 0.0
    streak = best_streak = 0
    for d in days_eval:
        p = float(d.get(pnl_key) or 0)
        eq += p
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        if p < 0:
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 0
    return {
        "n_days": len(days_eval),
        "roi": round(pnl / staked, 8) if staked > 1e-12 else None,
        "net_return": round(pnl, 6),
        "max_drawdown": round(dd, 6),
        "average_exposure": round(staked / n, 6),
        "active_day_ratio": round(len(active) / n, 8),
        "zero_capital_day_ratio": round((len(days_eval) - len(active)) / n, 8),
        "worst_losing_streak": best_streak,
        "maximum_daily_loss": round(
            min((float(d.get(pnl_key) or 0) for d in days_eval), default=0.0), 6
        ),
        "profitable_day_rate": round(
            sum(1 for d in days_eval if float(d.get(pnl_key) or 0) > 0) / n, 8
        ),
    }


def _unit_pnl_for_selection(day: dict[str, Any], selected_ids: list[int], scale: float) -> float:
    by_id = {int(f["fixture_id"]): f for f in (day.get("fixtures") or [])}
    pnl = 0.0
    for fid in selected_ids:
        fx = by_id.get(int(fid))
        if not fx or scale <= 0:
            continue
        if fx.get("hit_insurance") is True:
            odd = float(fx.get("insurance_odds") or fx.get("odds_home") or 2.0)
            pnl += scale * (odd - 1.0)
        elif fx.get("hit_insurance") is False:
            pnl -= scale
    return pnl


def always_bet_day(day: dict[str, Any]) -> tuple[float, float]:
    pnl = 0.0
    exp = 0.0
    for fx in day.get("fixtures") or []:
        exp += 1.0
        if fx.get("hit_insurance") is True:
            odd = float(fx.get("insurance_odds") or fx.get("odds_home") or 2.0)
            pnl += odd - 1.0
        elif fx.get("hit_insurance") is False:
            pnl -= 1.0
    return exp, pnl


def score_method_on_validation(
    train: list[dict[str, Any]],
    val: list[dict[str, Any]],
    feature_names: list[str],
    *,
    method: str,
    k: int,
    cfg: dict[str, Any],
    seed: int,
) -> dict[str, Any]:
    """Select method using validation analogs' label consistency (train library only)."""
    scaler = FeatureScaler().fit(matrix_from_days(train, feature_names), feature_names)
    Xtr = scaler.transform(matrix_from_days(train, feature_names))
    Xva = scaler.transform(matrix_from_days(val, feature_names))
    inv = stable_inv_cov(Xtr) if method == "mahalanobis" else None

    # Fit regimes on train
    k_info = choose_kmeans_k(Xtr, list(cfg.get("n_regimes_candidates") or [3, 4, 5]), seed=seed)
    regimes = fit_regimes(Xtr, method=str(cfg.get("regime_method") or "kmeans"), n_clusters=int(k_info["best_k"]), seed=seed)

    nn_dists = []
    analog_rois = []
    for i in range(len(val)):
        neigh = knn_indices(Xva[i], Xtr, k=k, method=method, inv_cov=inv)
        nn_dists.append(neigh[0][1] if neigh else 9.0)
        rois = []
        for idx, _ in neigh:
            r = train[idx].get("labels", {}).get("realized_roi")
            if r is not None:
                rois.append(float(r))
        if rois:
            analog_rois.append(float(np.mean(rois)))
    consistency = float(np.std(analog_rois)) if len(analog_rois) > 1 else 9.0
    mean_nn = float(np.mean(nn_dists)) if nn_dists else 9.0
    # lower consistency std + lower nn distance is better; higher mean analog roi better
    mean_roi = float(np.mean(analog_rois)) if analog_rois else -1.0
    rank = mean_roi - 0.5 * consistency - 0.1 * mean_nn
    return {
        "method": method,
        "k": k,
        "validation_rank_score": round(rank, 8),
        "mean_nn_distance": round(mean_nn, 8),
        "analog_roi_mean": round(mean_roi, 8),
        "analog_roi_std": round(consistency, 8),
        "best_k_regimes": k_info["best_k"],
        "silhouette": k_info.get("best_silhouette"),
    }


def analyze_day(
    day: dict[str, Any],
    *,
    library_days: list[dict[str, Any]],
    X_library: np.ndarray,
    x: np.ndarray,
    feature_names: list[str],
    method: str,
    k: int,
    inv_cov: np.ndarray | None,
    centroids: np.ndarray,
    global_mean: np.ndarray,
    train_min: np.ndarray,
    train_max: np.ndarray,
    nn_p95: float,
    centroid_p95: float,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    neigh = knn_indices(x, X_library, k=k, method=method, inv_cov=inv_cov)
    analogs = format_analogs(neigh, library_days)
    nn_dist = neigh[0][1] if neigh else 9.0
    regime_id, regime_conf = predict_regime(x, centroids)
    cent_dist = float(np.linalg.norm(x - centroids[regime_id]))
    missing_ratio = float(np.mean(np.isnan(matrix_from_days([day], feature_names))))
    ood = ood_status(
        x,
        nn_distance=nn_dist,
        nn_p95=nn_p95,
        centroid_distance=cent_dist,
        centroid_p95=centroid_p95,
        train_min=train_min,
        train_max=train_max,
        missing_ratio=missing_ratio,
        cfg=cfg,
    )
    rois = [a["historical_roi_evaluation_only"] for a in analogs if a["historical_roi_evaluation_only"] is not None]
    survivals = [a["coupon_survival"] for a in analogs if a["coupon_survival"] is not None]
    fails = [a["complete_coupon_failure"] for a in analogs if a["complete_coupon_failure"] is not None]
    dds = []
    for idx, _ in neigh:
        dds.append(float((library_days[idx].get("labels") or {}).get("drawdown_state") or 0))
    strength = float(np.mean([a["similarity_score"] for a in analogs])) if analogs else 0.0
    sim = day_similarity_quality_score(
        nn_similarity_strength=strength,
        analog_sample_size=len(analogs),
        analog_roi_mean=float(np.mean(rois)) if rois else None,
        analog_roi_std=float(np.std(rois)) if len(rois) > 1 else (0.0 if rois else None),
        analog_drawdown_mean=float(np.mean(dds)) if dds else None,
        analog_coupon_survival=float(np.mean(survivals)) if survivals else None,
        analog_failure_rate=float(np.mean(fails)) if fails else None,
        regime_confidence=regime_conf,
        feature_completeness=1.0 - missing_ratio,
        ood_level=ood["ood_level"],
        min_analog_count=int(cfg.get("min_analog_count", 5)),
    )
    profile = describe_regime(feature_names, centroids[regime_id], global_mean)
    return {
        "day_id": day.get("day_id"),
        "vienna_date": day.get("vienna_date"),
        "analogs": analogs,
        "regime_id": regime_id,
        "regime_confidence": round(regime_conf, 6),
        "regime_profile": profile,
        "ood": ood,
        "similarity": sim,
        "nn_distance": round(nn_dist, 8),
    }


def evaluate_policies_on_split(
    days: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
    *,
    overlay_cfg: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    for day, an in zip(days, analyses):
        exp_a, pnl_a = always_bet_day(day)
        # baseline
        b_sel = list(day.get("baseline_selected_fixture_ids") or [])
        b_exp = float(day.get("baseline_exposure") or 0)
        b_scale = (b_exp / len(b_sel)) if b_sel and b_exp > 0 else 0.0
        b_pnl = _unit_pnl_for_selection(day, b_sel, b_scale if b_scale > 0 else 1.0) if b_sel else 0.0
        if b_sel and b_scale == 0:
            b_pnl = 0.0
        # calibrated
        c_sel = list(day.get("calibrated_selected_fixture_ids") or [])
        c_exp = float(day.get("calibrated_exposure") or 0)
        c_scale = (c_exp / len(c_sel)) if c_sel and c_exp > 0 else (1.0 if c_sel else 0.0)
        c_pnl = _unit_pnl_for_selection(day, c_sel, c_scale) if c_sel else 0.0

        ov = apply_similarity_overlay(
            base_action=str(day.get("baseline_action") or "WATCH_NO_CAPITAL"),
            base_exposure=b_exp,
            base_selected_fixture_ids=b_sel,
            similarity_recommendation=str((an.get("similarity") or {}).get("recommendation")),
            ood_level=str((an.get("ood") or {}).get("ood_level")),
            overlay_cfg=overlay_cfg,
        )
        o_sel = list(ov.get("selected_fixture_ids") or [])
        o_exp = float(ov.get("exposure_units") or 0)
        o_scale = (o_exp / len(o_sel)) if o_sel and o_exp > 0 else 0.0
        o_pnl = _unit_pnl_for_selection(day, o_sel, o_scale) if o_sel and o_scale > 0 else 0.0

        # calibrated + overlay
        ov_c = apply_similarity_overlay(
            base_action=str(day.get("calibrated_action") or "WATCH_NO_CAPITAL"),
            base_exposure=c_exp,
            base_selected_fixture_ids=c_sel,
            similarity_recommendation=str((an.get("similarity") or {}).get("recommendation")),
            ood_level=str((an.get("ood") or {}).get("ood_level")),
            overlay_cfg=overlay_cfg,
        )
        oc_sel = list(ov_c.get("selected_fixture_ids") or [])
        oc_exp = float(ov_c.get("exposure_units") or 0)
        oc_scale = (oc_exp / len(oc_sel)) if oc_sel and oc_exp > 0 else 0.0
        oc_pnl = _unit_pnl_for_selection(day, oc_sel, oc_scale) if oc_sel and oc_scale > 0 else 0.0

        rows.append(
            {
                **day,
                "always_exposure": exp_a,
                "always_pnl": pnl_a,
                "baseline_pnl": b_pnl,
                "calibrated_pnl": c_pnl,
                "overlay_exposure": o_exp,
                "overlay_pnl": o_pnl,
                "overlay_action": ov.get("overlay_action"),
                "overlay_day_action": ov.get("action"),
                "cal_overlay_exposure": oc_exp,
                "cal_overlay_pnl": oc_pnl,
                "similarity_recommendation": (an.get("similarity") or {}).get("recommendation"),
                "ood_level": (an.get("ood") or {}).get("ood_level"),
                "similarity_score": (an.get("similarity") or {}).get("day_similarity_quality_score"),
            }
        )

    return {
        "always_bet": _summarize_pnl(rows, "always_exposure", "always_pnl"),
        "baseline_portfolio": _summarize_pnl(rows, "baseline_exposure", "baseline_pnl"),
        "calibrated_candidate": _summarize_pnl(rows, "calibrated_exposure", "calibrated_pnl"),
        "baseline_plus_similarity_overlay": _summarize_pnl(rows, "overlay_exposure", "overlay_pnl"),
        "calibrated_plus_similarity_overlay": _summarize_pnl(rows, "cal_overlay_exposure", "cal_overlay_pnl"),
        "rows": rows,
    }


def check_success_criteria(holdout_cmp: dict[str, Any]) -> dict[str, Any]:
    always = holdout_cmp["always_bet"]
    base = holdout_cmp["baseline_portfolio"]
    overlay = holdout_cmp["baseline_plus_similarity_overlay"]
    checks = {
        "overlay_roi_ge_baseline": (
            overlay.get("roi") is not None
            and base.get("roi") is not None
            and overlay["roi"] >= base["roi"]
        ),
        "overlay_dd_le_baseline": float(overlay.get("max_drawdown") or 0) <= float(base.get("max_drawdown") or 0) + 1e-9,
        "overlay_exposure_controlled": float(overlay.get("average_exposure") or 0)
        <= float(always.get("average_exposure") or 1) * 0.70,
        "strong_roi_ge_always": (
            overlay.get("roi") is not None
            and always.get("roi") is not None
            and overlay["roi"] >= always["roi"]
        ),
        "strong_dd_below_always": float(overlay.get("max_drawdown") or 9e9)
        <= 0.75 * float(always.get("max_drawdown") or 1),
        "alt_roi_approx_unchanged": (
            overlay.get("roi") is not None
            and base.get("roi") is not None
            and abs(overlay["roi"] - base["roi"]) <= 0.05
        ),
        "alt_meaningful_dd_reduction": float(overlay.get("max_drawdown") or 0)
        <= float(base.get("max_drawdown") or 0) - 0.25,
    }
    preferred = checks["overlay_roi_ge_baseline"] and checks["overlay_dd_le_baseline"] and checks["overlay_exposure_controlled"]
    strong = checks["strong_roi_ge_always"] and checks["strong_dd_below_always"]
    alt = checks["alt_roi_approx_unchanged"] and checks["alt_meaningful_dd_reduction"]
    success = preferred or strong or alt
    return {
        "checks": checks,
        "passed": {k: v for k, v in checks.items() if v},
        "failed": {k: v for k, v in checks.items() if not v},
        "preferred_success": preferred,
        "strong_success": strong,
        "alternative_success": alt,
        "any_success": success,
    }
