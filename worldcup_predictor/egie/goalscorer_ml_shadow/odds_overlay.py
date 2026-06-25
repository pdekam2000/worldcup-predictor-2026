"""Odds overlay research for goalscorer ML shadow."""

from __future__ import annotations

from typing import Any

import pandas as pd

from worldcup_predictor.egie.goalscorer_shadow.validation import align_odds_with_model


def run_odds_overlay(test_df: pd.DataFrame, score_col: str = "score_ensemble") -> dict[str, Any]:
    if test_df.empty or score_col not in test_df.columns:
        return {"status": "no_data"}
    result = align_odds_with_model(test_df, score_col=score_col)
    agreement = result.get("anytime_top1_overlap_rate")
    disagreement = round(1.0 - (agreement or 0.0), 4) if agreement is not None else None
    return {
        **result,
        "agreement_pct": agreement,
        "disagreement_pct": disagreement,
        "potential_edge_fixtures": len(result.get("disagreement_samples") or []),
        "worth_integrating_later": bool(result.get("fixtures_with_odds", 0) >= 30 and not result.get("mapping_blocker")),
    }
