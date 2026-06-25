"""Before/after revalidation for Phase 55B."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss

from worldcup_predictor.egie.goalscorer_intelligence.feature_pipeline import attach_ml_scores, enrich_intelligence_features
from worldcup_predictor.egie.goalscorer_intelligence.generalization import league_split_validation
from worldcup_predictor.egie.goalscorer_intelligence.validation import fixture_ranking_hits
from worldcup_predictor.egie.goalscorer_ml_shadow.calibration import expected_calibration_error
from worldcup_predictor.egie.goalscorer_uefa_expansion.models import (
    BASELINE_54Q_UEFA_TOP3,
    BASELINE_54Q_OVERALL_TOP3,
    UEFA_LEAGUE_IDS,
)


def _intel_frame(df: pd.DataFrame) -> pd.DataFrame:
    scored = attach_ml_scores(df)
    return enrich_intelligence_features(scored)


def _metrics_block(df: pd.DataFrame, *, label: str) -> dict[str, Any]:
    intel = _intel_frame(df)
    uefa_ids = set(UEFA_LEAGUE_IDS.keys())

    overall = fixture_ranking_hits(intel, score_col="composite_scorer_score", target_col="target_anytime")
    uefa = intel[intel["league_id"].isin(uefa_ids)]
    uefa_hits = fixture_ranking_hits(uefa, score_col="composite_scorer_score", target_col="target_anytime")

    with_odds = intel[intel["has_goalscorer_odds"] == 1]
    odds_hits = fixture_ranking_hits(with_odds, score_col="composite_scorer_score", target_col="target_anytime")

    blend = intel.copy()
    blend["ml_odds_blend"] = 0.6 * blend["ml_score"].fillna(0) + 0.4 * blend["odds_implied_anytime"].fillna(0)
    blend_hits = fixture_ranking_hits(blend, score_col="ml_odds_blend", target_col="target_anytime")

    cal = _calibration(intel, "composite_scorer_score")
    leagues = league_split_validation(intel)

    fixtures_with_odds = int(intel.loc[intel["has_goalscorer_odds"] == 1, "sportmonks_fixture_id"].nunique())
    total_fixtures = int(intel["sportmonks_fixture_id"].nunique())

    return {
        "label": label,
        "fixtures_total": total_fixtures,
        "fixtures_with_odds": fixtures_with_odds,
        "odds_coverage_pct": round(fixtures_with_odds / total_fixtures, 4) if total_fixtures else 0.0,
        "overall": overall.to_dict(),
        "uefa": uefa_hits.to_dict(),
        "with_odds_only": odds_hits.to_dict(),
        "ml_odds_blend": blend_hits.to_dict(),
        "calibration": cal,
        "league_split": leagues,
    }


def _calibration(df: pd.DataFrame, score_col: str) -> dict[str, Any]:
    sub = df[df[score_col].notna() & df["target_anytime"].notna()].copy()
    if sub.empty:
        return {"n": 0}
    y = sub["target_anytime"].astype(int).values
    p = np.clip(sub[score_col].astype(float).values, 1e-6, 1 - 1e-6)
    return {
        "n": len(sub),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "ece": expected_calibration_error(y, p),
    }


def run_before_after(
    before_df: pd.DataFrame,
    after_df: pd.DataFrame,
) -> dict[str, Any]:
    before = _metrics_block(before_df, label="before_expansion")
    after = _metrics_block(after_df, label="after_expansion")

    uefa_before = float((before.get("uefa") or {}).get("top3_hit") or BASELINE_54Q_UEFA_TOP3)
    uefa_after = float((after.get("uefa") or {}).get("top3_hit") or 0)
    overall_before = float((before.get("overall") or {}).get("top3_hit") or BASELINE_54Q_OVERALL_TOP3)
    overall_after = float((after.get("overall") or {}).get("top3_hit") or 0)

    cov_before = float(before.get("odds_coverage_pct") or 0)
    cov_after = float(after.get("odds_coverage_pct") or 0)

    uefa_odds_before = int(before.get("fixtures_with_odds") or 0)
    uefa_odds_after = int(after.get("fixtures_with_odds") or 0)

    return {
        "before": before,
        "after": after,
        "delta": {
            "overall_top3_pp": round(overall_after - overall_before, 4),
            "uefa_top3_pp": round(uefa_after - uefa_before, 4),
            "odds_coverage_pp": round(cov_after - cov_before, 4),
            "fixtures_with_odds_delta": uefa_odds_after - uefa_odds_before,
            "brier_delta": round(
                float((after.get("calibration") or {}).get("brier") or 0)
                - float((before.get("calibration") or {}).get("brier") or 0),
                4,
            ),
            "ece_delta": round(
                float((after.get("calibration") or {}).get("ece") or 0)
                - float((before.get("calibration") or {}).get("ece") or 0),
                4,
            ),
        },
        "impact": analyze_impact(before, after, uefa_before, uefa_after, cov_before, cov_after),
    }


def analyze_impact(
    before: dict[str, Any],
    after: dict[str, Any],
    uefa_before: float,
    uefa_after: float,
    cov_before: float,
    cov_after: float,
) -> dict[str, Any]:
    """Part E — how much of UEFA weakness is solved by odds."""
    gap_to_wc = 0.7714 - uefa_before
    closed_by_odds = uefa_after - uefa_before
    pct_solved = round(closed_by_odds / gap_to_wc, 4) if gap_to_wc > 0 else 0.0

    uefa_with_odds_after = float((after.get("uefa") or {}).get("top3_hit") or 0)
    blend_uefa = after.get("league_split") or {}

    return {
        "uefa_weakness_baseline_top3": uefa_before,
        "uefa_after_expansion_top3": uefa_after,
        "wc_reference_top3": 0.7714,
        "gap_to_wc_before": round(gap_to_wc, 4),
        "gap_closed_pp": round(closed_by_odds, 4),
        "pct_of_gap_solved": pct_solved,
        "coverage_before_pct": cov_before,
        "coverage_after_pct": cov_after,
        "coverage_gain_pp": round(cov_after - cov_before, 4),
        "odds_insufficient_for_elite": cov_after < 0.10,
        "uefa_still_below_65": uefa_after < 0.65,
    }


def decide_recommendation(impact: dict[str, Any], reval: dict[str, Any]) -> dict[str, Any]:
    uefa_top3 = float(impact.get("uefa_after_expansion_top3") or 0)
    cov_after = float(impact.get("coverage_after_pct") or 0)
    pct_solved = float(impact.get("pct_of_gap_solved") or 0)
    delta_uefa = float((reval.get("delta") or {}).get("uefa_top3_pp") or 0)

    if uefa_top3 >= 0.70 and cov_after >= 0.15:
        rec = "GOALSCORER_ELITE_PATH"
    elif delta_uefa >= 0.02 or pct_solved >= 0.15:
        rec = "GOALSCORER_HIGH_VALUE"
    else:
        rec = "ODDS_NOT_ENOUGH"

    return {
        "recommendation": rec,
        "uefa_top3_after": uefa_top3,
        "coverage_after": cov_after,
        "pct_gap_solved": pct_solved,
    }
