"""ML vs bookmaker edge analysis on bridged fixtures."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def run_edge_analysis(comparison_df: pd.DataFrame, *, target_col: str = "target_anytime") -> dict[str, Any]:
    if comparison_df.empty:
        return {"status": "no_data", "edge_value": "LOW"}

    fixtures = comparison_df["sportmonks_fixture_id"].unique()
    agree = disagree = 0
    disagree_hits = 0
    disagree_n = 0
    ml_strong_disagree = 0
    book_strong_disagree = 0

    for fid in fixtures:
        grp = comparison_df[comparison_df["sportmonks_fixture_id"] == fid]
        positives = grp[grp[target_col] == 1]
        if positives.empty:
            continue

        ml_top = set(grp.nlargest(3, "ml_probability")["player_id"].astype(int).tolist())
        bk_top = set(grp.nlargest(3, "implied_probability")["player_id"].astype(int).tolist())
        pos_ids = set(positives["player_id"].astype(int).tolist())

        if ml_top & bk_top:
            agree += 1
        else:
            disagree += 1
            disagree_n += 1
            hit = bool(pos_ids & (ml_top | bk_top))
            if hit:
                disagree_hits += 1

        # strong disagreement diagnostics (no extra hit-rate credit)
        merged = grp.copy()
        if len(merged) >= 3:
            top_ml = merged.nlargest(1, "ml_probability").iloc[0]
            top_bk = merged.nlargest(1, "implied_probability").iloc[0]
            if int(top_ml["player_id"]) != int(top_bk["player_id"]):
                if float(top_ml["ml_probability"]) > float(top_bk["implied_probability"]) * 1.5:
                    ml_strong_disagree += 1
                elif float(top_bk["implied_probability"]) > float(top_ml["ml_probability"]) * 1.5:
                    book_strong_disagree += 1

    evaluated = agree + disagree
    agreement_pct = round(agree / evaluated, 4) if evaluated else 0.0
    disagreement_pct = round(disagree / evaluated, 4) if evaluated else 0.0
    disagree_hit_rate = round(disagree_hits / max(disagree_n, 1), 4)

    if disagreement_pct > 0.5 and disagree_hit_rate >= 0.35:
        edge_value = "HIGH"
    elif disagree_hit_rate >= 0.25 or agreement_pct < 0.7:
        edge_value = "MEDIUM"
    else:
        edge_value = "LOW"

    return {
        "status": "ok",
        "fixtures_evaluated": evaluated,
        "agreement_pct": agreement_pct,
        "disagreement_pct": disagreement_pct,
        "disagree_group_hit_rate": disagree_hit_rate,
        "ml_strong_disagree_fixtures": ml_strong_disagree,
        "book_strong_disagree_fixtures": book_strong_disagree,
        "edge_value": edge_value,
    }
