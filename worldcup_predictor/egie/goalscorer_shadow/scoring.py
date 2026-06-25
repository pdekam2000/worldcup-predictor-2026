"""Simple shadow baseline scorers for goalscorer markets."""

from __future__ import annotations

import numpy as np
import pandas as pd

from worldcup_predictor.egie.goalscorer_shadow.models import SCORE_COLUMNS


def _norm_series(s: pd.Series) -> pd.Series:
    if s.empty:
        return s
    mx = float(s.max())
    return s / mx if mx > 0 else s


def apply_baseline_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Add goals_per_90_score, xg_per_90_score, starter_weighted_score, combined_score."""
    out = df.copy()
    gp90 = out["goals_per_90"].fillna(0.0) * out["starter_probability"].fillna(0.0)
    xgp90 = out["xg_per_90"].fillna(0.0) * out["starter_probability"].fillna(0.0)
    form = out["recent_form_score"].fillna(0.0) * out["starter_probability"].fillna(0.0)

    out["goals_per_90_score"] = gp90
    out["xg_per_90_score"] = xgp90
    out["starter_weighted_score"] = form + out["goals_last_5"].fillna(0) * 0.15

    out["combined_score"] = (
        0.45 * _norm_series(gp90)
        + 0.25 * _norm_series(xgp90)
        + 0.20 * _norm_series(form)
        + 0.10 * _norm_series(out["team_strength_proxy"].fillna(0.0))
    )
    return out


def rank_players_per_fixture(
    df: pd.DataFrame,
    score_col: str,
    *,
    split: str | None = None,
) -> pd.DataFrame:
    sub = df if split is None else df[df["split"] == split]
    if sub.empty:
        return sub
    ranked = sub.copy()
    ranked["rank"] = (
        ranked.groupby("sportmonks_fixture_id")[score_col]
        .rank(ascending=False, method="first")
        .astype(int)
    )
    return ranked


def naive_uniform_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Naive baseline: equal score for all eligible players in fixture."""
    out = df.copy()
    out["naive_score"] = 1.0
    return out
