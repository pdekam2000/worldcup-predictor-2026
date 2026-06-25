"""Ranking engine for goalscorer intelligence."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _rank_within_fixture(df: pd.DataFrame, score_col: str, *, ascending: bool = False) -> pd.Series:
    return df.groupby("sportmonks_fixture_id")[score_col].rank(ascending=ascending, method="first")


def add_ranks(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ml_rank"] = _rank_within_fixture(out, "ml_score", ascending=False)
    out["odds_rank"] = _rank_within_fixture(out, "odds_implied_anytime", ascending=False)
    out["composite_rank"] = _rank_within_fixture(out, "composite_scorer_score", ascending=False)
    out["first_goal_rank"] = _rank_within_fixture(out, "composite_first_goal_score", ascending=False)
    out["value_gap"] = (out["odds_rank"].fillna(99) - out["ml_rank"]).round(2)
    return out


def top_n_players(grp: pd.DataFrame, score_col: str, n: int = 5) -> list[dict[str, Any]]:
    cols = [
        "player_id",
        "player_name",
        "team_id",
        score_col,
        "ml_score",
        "odds_implied_anytime",
        "confidence_tier",
        "ml_rank",
        "odds_rank",
    ]
    avail = [c for c in cols if c in grp.columns]
    top = grp.nlargest(n, score_col)[avail]
    return top.to_dict(orient="records")


def identify_surprise_candidates(grp: pd.DataFrame, n: int = 5) -> list[dict[str, Any]]:
    """High ML/form but low book expectation or bench role."""
    sub = grp.copy()
    sub["surprise_score"] = (
        sub["ml_norm"] * 0.5
        + sub["form_norm"] * 0.3
        + (1.0 - sub["odds_norm"]) * 0.2
    )
    filtered = sub[(sub["ml_rank"] <= 10) & (sub["odds_rank"] >= 8)]
    if not filtered.empty:
        sub = filtered
    return top_n_players(sub, "surprise_score", n)


def identify_value_picks(grp: pd.DataFrame, n: int = 5, *, min_gap: float = 5.0) -> list[dict[str, Any]]:
    sub = grp[grp["value_gap"] >= min_gap].copy()
    if sub.empty:
        sub = grp.nlargest(min(n, len(grp)), "value_gap").copy()
    sub["value_score"] = sub["value_gap"] * sub["ml_norm"]
    return top_n_players(sub, "value_score", n)


def team_scoring_threats(grp: pd.DataFrame, n: int = 2) -> list[dict[str, Any]]:
    if "team_id" not in grp.columns:
        return []
    agg = (
        grp.groupby("team_id", as_index=False)
        .agg(
            team_threat_score=("composite_scorer_score", "sum"),
            top_player=("player_name", "first"),
            avg_ml=("ml_score", "mean"),
            avg_odds=("odds_implied_anytime", "mean"),
        )
        .sort_values("team_threat_score", ascending=False)
        .head(n)
    )
    return agg.to_dict(orient="records")
