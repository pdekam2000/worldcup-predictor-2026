"""ML vs bookmaker comparison for mapped goalscorer odds."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from worldcup_predictor.egie.goalscorer_odds_mapping.models import USABLE_CONFIDENCES


def _rank_group(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    out = df.copy()
    out["rank"] = out.groupby("sportmonks_fixture_id")[score_col].rank(ascending=False, method="first")
    return out


def build_comparison_frame(
    mapped_df: pd.DataFrame,
    outcomes_df: pd.DataFrame,
    ml_scores: pd.DataFrame,
    *,
    market_label: str = "Anytime",
) -> pd.DataFrame:
    """Join mapped odds, ML scores, and outcomes for one market label."""
    odds = mapped_df[
        mapped_df["mapping_confidence"].isin(USABLE_CONFIDENCES)
        & mapped_df["label"].str.contains(market_label, case=False, na=False)
    ].copy()
    if odds.empty:
        return pd.DataFrame()

    # consensus implied per player-fixture (mean across books)
    consensus = (
        odds.groupby(["sportmonks_fixture_id", "player_id"], as_index=False)
        .agg(implied_probability=("implied_probability", "mean"), odds=("odds", "mean"))
    )

    ml = ml_scores[["sportmonks_fixture_id", "player_id", "ml_probability"]].copy()
    out = consensus.merge(ml, on=["sportmonks_fixture_id", "player_id"], how="inner")
    out = out.merge(
        outcomes_df[["sportmonks_fixture_id", "player_id", "target_anytime", "player_name"]],
        on=["sportmonks_fixture_id", "player_id"],
        how="left",
    )
    out["ml_odds_blend"] = 0.6 * out["ml_probability"] + 0.4 * out["implied_probability"]
    out["market_adjusted_ml"] = out["ml_probability"] * (1.0 + 0.15 * out["implied_probability"])
    return out


def fixture_ranking_metrics(
    df: pd.DataFrame,
    score_col: str,
    target_col: str = "target_anytime",
) -> dict[str, Any]:
    if df.empty:
        return {"fixtures": 0}
    ranked = _rank_group(df, score_col)
    fixtures = ranked["sportmonks_fixture_id"].unique()
    top1 = top3 = top5 = 0
    ml_only = book_only = combined = 0
    overlap3 = disagree3 = 0
    evaluated = 0

    for fid in fixtures:
        grp = ranked[ranked["sportmonks_fixture_id"] == fid]
        positives = grp[grp[target_col] == 1]["player_id"].astype(int).tolist()
        if not positives:
            continue
        evaluated += 1
        top = grp.sort_values("rank")
        top_ids = top.head(5)["player_id"].astype(int).tolist()
        if any(pid in positives for pid in top_ids[:1]):
            top1 += 1
        if any(pid in positives for pid in top_ids[:3]):
            top3 += 1
        if any(pid in positives for pid in top_ids[:5]):
            top5 += 1

    # overlap ML vs book top-3
    if "ml_probability" in df.columns and "implied_probability" in df.columns and target_col in df.columns:
        for fid in fixtures:
            grp = df[df["sportmonks_fixture_id"] == fid]
            if grp[target_col].sum() == 0:
                continue
            ml_top = set(grp.nlargest(3, "ml_probability")["player_id"].astype(int).tolist())
            bk_top = set(grp.nlargest(3, "implied_probability")["player_id"].astype(int).tolist())
            if ml_top & bk_top:
                overlap3 += 1
            else:
                disagree3 += 1
            pos = set(grp[grp[target_col] == 1]["player_id"].astype(int).tolist())
            if pos & ml_top and not pos & bk_top:
                ml_only += 1
            elif pos & bk_top and not pos & ml_top:
                book_only += 1
            elif pos & ml_top and pos & bk_top:
                combined += 1

    n = evaluated or 1
    n_od = max(overlap3 + disagree3, 1)
    return {
        "fixtures_evaluated": evaluated,
        "top1_hit": round(top1 / n, 4),
        "top3_hit": round(top3 / n, 4),
        "top5_hit": round(top5 / n, 4),
        "overlap_top3_rate": round(overlap3 / n_od, 4),
        "disagreement_top3_rate": round(disagree3 / n_od, 4),
        "ml_only_hit_rate": round(ml_only / n, 4),
        "bookmaker_only_hit_rate": round(book_only / n, 4),
        "combined_signal_hit_rate": round(combined / n, 4),
    }


def run_comparison(comparison_df: pd.DataFrame) -> dict[str, Any]:
    if comparison_df.empty:
        return {"status": "no_mapped_rows"}
    scores = {
        "ml_probability": "ml_probability",
        "implied_probability": "implied_probability",
        "ml_odds_blend": "ml_odds_blend",
        "market_adjusted_ml": "market_adjusted_ml",
    }
    results = {name: fixture_ranking_metrics(comparison_df, col) for name, col in scores.items()}
    return {
        "status": "ok",
        "rows": len(comparison_df),
        "fixtures": int(comparison_df["sportmonks_fixture_id"].nunique()),
        "metrics": results,
    }
