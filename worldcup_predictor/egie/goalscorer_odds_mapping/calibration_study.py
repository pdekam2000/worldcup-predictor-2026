"""Calibration study for ML vs odds goalscorer probabilities."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss

from worldcup_predictor.egie.goalscorer_ml_shadow.calibration import (
    calibration_curve_bins,
    expected_calibration_error,
    isotonic_calibrate,
    platt_calibrate,
)


def evaluate_probability_track(
    df: pd.DataFrame,
    prob_col: str,
    target_col: str = "target_anytime",
) -> dict[str, Any]:
    sub = df[df[prob_col].notna() & df[target_col].notna()].copy()
    if sub.empty:
        return {"n": 0}
    y = sub[target_col].astype(int).values
    p = np.clip(sub[prob_col].astype(float).values, 1e-6, 1 - 1e-6)
    return {
        "n": len(sub),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "logloss": round(float(log_loss(y, p)), 4),
        "ece": expected_calibration_error(y, p),
        "curve": calibration_curve_bins(y, p),
    }


def run_calibration_study(
    comparison_df: pd.DataFrame,
    val_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    if comparison_df.empty:
        return {"status": "insufficient_rows"}

    tracks = {
        "ml_only": "ml_probability",
        "odds_only": "implied_probability",
        "ml_odds_blend": "ml_odds_blend",
        "market_adjusted_ml": "market_adjusted_ml",
    }
    raw_results = {name: evaluate_probability_track(comparison_df, col) for name, col in tracks.items()}

    # Platt on blend using val split if available
    calibrated = {}
    if val_df is not None and not val_df.empty and "ml_odds_blend" in val_df.columns:
        y_val = val_df["target_anytime"].astype(int).values
        p_val = val_df["ml_odds_blend"].astype(float).values
        y_test = comparison_df["target_anytime"].astype(int).values
        p_test = comparison_df["ml_odds_blend"].astype(float).values
        p_platt = platt_calibrate(y_val, p_val, p_test)
        p_iso = isotonic_calibrate(y_val, p_val, p_test)
        calibrated["blend_platt"] = evaluate_probability_track(
            comparison_df.assign(blend_platt=p_platt), "blend_platt"
        )
        calibrated["blend_isotonic"] = evaluate_probability_track(
            comparison_df.assign(blend_isotonic=p_iso), "blend_isotonic"
        )

    # ranking from probability tracks
    ranking = {}
    from worldcup_predictor.egie.goalscorer_odds_mapping.comparison import fixture_ranking_metrics

    for name, col in tracks.items():
        if col in comparison_df.columns:
            ranking[name] = fixture_ranking_metrics(comparison_df, col)

    return {
        "status": "ok",
        "raw": raw_results,
        "calibrated": calibrated,
        "ranking_by_track": ranking,
        "ml_beats_odds_top3": (
            (ranking.get("ml_only") or {}).get("top3_hit", 0)
            > (ranking.get("odds_only") or {}).get("top3_hit", 0)
        ),
        "blend_beats_ml_top3": (
            (ranking.get("ml_odds_blend") or {}).get("top3_hit", 0)
            > (ranking.get("ml_only") or {}).get("top3_hit", 0)
        ),
    }
