"""Research-only probability calibration for goalscorer shadow scores."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def softmax_by_fixture(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    out = df.copy()
    probs: list[float] = []
    for _, grp in out.groupby("sportmonks_fixture_id"):
        scores = grp[score_col].fillna(0.0).astype(float).values
        if scores.sum() <= 0:
            p = np.ones(len(scores)) / len(scores)
        else:
            exp = np.exp(scores - scores.max())
            p = exp / exp.sum()
        probs.extend(p.tolist())
    out["raw_score"] = out[score_col]
    out["normalized_probability"] = probs
    return out


def confidence_tier(prob: float) -> str:
    if prob >= 0.25:
        return "high"
    if prob >= 0.12:
        return "medium"
    if prob >= 0.05:
        return "low"
    return "minimal"


def apply_calibration(df: pd.DataFrame, score_col: str = "combined_score") -> pd.DataFrame:
    """Add raw_score, normalized_probability, confidence_tier (research only)."""
    calibrated = softmax_by_fixture(df, score_col)
    calibrated["confidence_tier"] = calibrated["normalized_probability"].apply(confidence_tier)
    return calibrated


def calibration_summary(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty or "normalized_probability" not in df.columns:
        return {}
    scored = df[df["target_anytime"] == 1]
    bins = [0, 0.05, 0.12, 0.25, 1.0]
    rows = []
    for i in range(len(bins) - 1):
        mask = (df["normalized_probability"] >= bins[i]) & (df["normalized_probability"] < bins[i + 1])
        if not mask.any():
            continue
        rows.append({
            "bin": f"{bins[i]:.2f}-{bins[i+1]:.2f}",
            "n": int(mask.sum()),
            "actual_rate": round(float(df.loc[mask, "target_anytime"].mean()), 4),
            "mean_prob": round(float(df.loc[mask, "normalized_probability"].mean()), 4),
        })
    return {
        "bins": rows,
        "scorer_mean_prob": round(float(scored["normalized_probability"].mean()), 4) if len(scored) else None,
    }
