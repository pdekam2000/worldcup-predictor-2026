"""WC vs UEFA performance comparison and counterfactual odds impact."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss

from worldcup_predictor.egie.goalscorer_intelligence.generalization import _recompute_composite
from worldcup_predictor.egie.goalscorer_intelligence.generalization_models import LEAGUE_LABELS
from worldcup_predictor.egie.goalscorer_intelligence.uefa_odds_audit.models import UEFA_LEAGUE_IDS, WC_LEAGUE_ID
from worldcup_predictor.egie.goalscorer_intelligence.validation import fixture_ranking_hits
from worldcup_predictor.egie.goalscorer_ml_shadow.calibration import expected_calibration_error


def _segment(df: pd.DataFrame, *, league_ids: set[int] | None = None, with_odds: bool | None = None) -> pd.DataFrame:
    out = df.copy()
    if league_ids is not None:
        out = out[out["league_id"].isin(league_ids)]
    if with_odds is not None:
        flag = out.get("has_goalscorer_odds", (out["odds_implied_anytime"].notna()).astype(int))
        out = out[flag == (1 if with_odds else 0)]
    return out


def _metrics_block(df: pd.DataFrame, score_col: str) -> dict[str, Any]:
    hits = fixture_ranking_hits(df, score_col=score_col, target_col="target_anytime")
    cal = _calibration(df, score_col)
    tiers = _tier_top3(df, score_col)
    return {"ranking": hits.to_dict(), "calibration": cal, "confidence_tiers_top3": tiers}


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


def _tier_top3(df: pd.DataFrame, score_col: str) -> dict[str, float]:
    if "confidence_tier" not in df.columns:
        return {}
    out: dict[str, float] = {}
    for tier, grp in df.groupby("confidence_tier"):
        h = fixture_ranking_hits(grp, score_col=score_col, target_col="target_anytime")
        out[str(tier)] = h.top3_hit
    return out


def compare_wc_vs_uefa(df: pd.DataFrame) -> dict[str, Any]:
    uefa_ids = set(UEFA_LEAGUE_IDS.keys())
    segments = {
        "world_cup_with_odds": _segment(df, league_ids={WC_LEAGUE_ID}, with_odds=True),
        "world_cup_all": _segment(df, league_ids={WC_LEAGUE_ID}),
        "uefa_with_odds": _segment(df, league_ids=uefa_ids, with_odds=True),
        "uefa_without_odds": _segment(df, league_ids=uefa_ids, with_odds=False),
        "uefa_all": _segment(df, league_ids=uefa_ids),
    }

    results: dict[str, Any] = {}
    for name, seg in segments.items():
        if seg.empty:
            results[name] = {"status": "empty", "fixtures": 0}
            continue
        results[name] = {
            "fixtures": int(seg["sportmonks_fixture_id"].nunique()),
            "composite": _metrics_block(seg, "composite_scorer_score"),
            "ml_only": _metrics_block(seg, "ml_score"),
            "odds_only": _metrics_block(seg, "odds_implied_anytime"),
            "ml_odds_blend": _metrics_block(
                seg.assign(ml_odds_blend=0.6 * seg["ml_score"].fillna(0) + 0.4 * seg["odds_implied_anytime"].fillna(0)),
                "ml_odds_blend",
            ),
        }
    return results


def odds_lift_on_wc(df: pd.DataFrame) -> dict[str, Any]:
    """Measured odds contribution on WC sample where odds exist."""
    wc = _segment(df, league_ids={WC_LEAGUE_ID}, with_odds=True)
    if wc.empty:
        return {"status": "no_wc_odds"}

    baseline = fixture_ranking_hits(wc, score_col="composite_scorer_score")
    ml = fixture_ranking_hits(wc, score_col="ml_score")
    blend = fixture_ranking_hits(
        wc.assign(ml_odds_blend=0.6 * wc["ml_score"].fillna(0) + 0.4 * wc["odds_implied_anytime"].fillna(0)),
        score_col="ml_odds_blend",
    )
    no_odds = wc.copy()
    no_odds["composite_no_odds"] = _recompute_composite(no_odds, drop={"odds"})
    ablated = fixture_ranking_hits(no_odds, score_col="composite_no_odds")

    return {
        "fixtures_evaluated": baseline.fixtures_evaluated,
        "composite_top3": baseline.top3_hit,
        "ml_only_top3": ml.top3_hit,
        "blend_top3": blend.top3_hit,
        "composite_no_odds_top3": ablated.top3_hit,
        "odds_lift_top3_composite_vs_ml": round(baseline.top3_hit - ml.top3_hit, 4),
        "odds_lift_top3_blend_vs_ml": round(blend.top3_hit - ml.top3_hit, 4),
        "odds_lift_top3_composite_vs_no_odds": round(baseline.top3_hit - ablated.top3_hit, 4),
    }


def counterfactual_uefa_with_odds(df: pd.DataFrame, wc_lift: dict[str, Any]) -> dict[str, Any]:
    """Estimate plausible UEFA top-3 if odds coverage matched WC — no invented metrics."""
    uefa = _segment(df, league_ids=set(UEFA_LEAGUE_IDS.keys()))
    uefa_ml = fixture_ranking_hits(uefa, score_col="ml_score")
    uefa_comp = fixture_ranking_hits(uefa, score_col="composite_scorer_score")

    lift_blend = float(wc_lift.get("odds_lift_top3_blend_vs_ml") or 0)
    lift_comp = float(wc_lift.get("odds_lift_top3_composite_vs_ml") or 0)
    lift_no_odds = float(wc_lift.get("odds_lift_top3_composite_vs_no_odds") or 0)

    ml_top3 = uefa_ml.top3_hit
    estimates = {
        "uefa_current_ml_top3": ml_top3,
        "uefa_current_composite_top3": uefa_comp.top3_hit,
        "estimated_if_blend_lift": round(min(1.0, ml_top3 + lift_blend), 4),
        "estimated_if_composite_lift": round(min(1.0, ml_top3 + lift_comp), 4),
        "estimated_if_full_odds_ablation_reversed": round(min(1.0, uefa_comp.top3_hit + lift_no_odds), 4),
        "plausible_range_top3": [
            round(ml_top3 + min(lift_blend, lift_comp), 4),
            round(min(1.0, ml_top3 + max(lift_blend, lift_comp, lift_no_odds)), 4),
        ],
    }
    estimates["would_reach_70pct"] = estimates["plausible_range_top3"][1] >= 0.70
    estimates["assumptions"] = (
        "Applies measured WC odds lift to UEFA ML baseline; assumes comparable bookmaker quality and mapping."
    )
    return estimates


def feature_contribution_audit(df: pd.DataFrame) -> dict[str, Any]:
    """Per-segment ablation — quantify odds vs lineup vs form vs xG contribution."""
    segments = {
        "overall": df,
        "world_cup": _segment(df, league_ids={WC_LEAGUE_ID}),
        "uefa": _segment(df, league_ids=set(UEFA_LEAGUE_IDS.keys())),
    }
    drops = {
        "odds": {"odds"},
        "lineup": {"lineup"},
        "form": {"form"},
        "xg": {"xg"},
        "starter_probability": {"lineup"},
    }

    out: dict[str, Any] = {}
    for seg_name, seg in segments.items():
        if seg.empty:
            continue
        base = fixture_ranking_hits(seg, score_col="composite_scorer_score")
        base_top3 = base.top3_hit
        impacts: dict[str, float] = {}
        for feat, drop in drops.items():
            test = seg.copy()
            test["ablated"] = _recompute_composite(test, drop=drop)
            hits = fixture_ranking_hits(test, score_col="ablated")
            impacts[feat] = round(base_top3 - hits.top3_hit, 4)
        ranked = sorted(impacts.items(), key=lambda x: x[1], reverse=True)
        out[seg_name] = {
            "baseline_top3": base_top3,
            "feature_drops": impacts,
            "ranked_contributors": ranked,
            "odds_share_of_explained_lift": impacts.get("odds", 0.0),
        }
    return out


def decide_limitation(
    comparison: dict[str, Any],
    wc_lift: dict[str, Any],
    counterfactual: dict[str, Any],
    coverage: dict[str, Any],
    feature_audit: dict[str, Any],
) -> dict[str, Any]:
    uefa_cov = float((coverage.get("dataset_v3") or {}).get("uefa_coverage_pct") or 0)
    wc_top3 = float(
        ((comparison.get("world_cup_with_odds") or {}).get("composite") or {})
        .get("ranking", {})
        .get("top3_hit", 0)
    )
    uefa_top3 = float(
        ((comparison.get("uefa_without_odds") or {}).get("composite") or {})
        .get("ranking", {})
        .get("top3_hit", 0)
    )
    uefa_ml_top3 = float(
        ((comparison.get("uefa_all") or {}).get("ml_only") or {})
        .get("ranking", {})
        .get("top3_hit", 0)
    )
    odds_lift = float(wc_lift.get("odds_lift_top3_blend_vs_ml") or 0)
    would_reach_70 = bool(counterfactual.get("would_reach_70pct"))

    uefa_odds_starved = uefa_cov < 0.05
    wc_odds_helped = odds_lift >= 0.05
    model_ceiling = uefa_ml_top3 < 0.60

    if uefa_odds_starved and wc_odds_helped and would_reach_70:
        recommendation = "EXPAND_UEFA_GOALSCORER_ODDS"
        primary = "B_odds"
    elif uefa_odds_starved and wc_odds_helped and not would_reach_70 and model_ceiling:
        recommendation = "BOTH_LIMITED"
        primary = "C_both"
    elif uefa_odds_starved and wc_odds_helped:
        recommendation = "EXPAND_UEFA_GOALSCORER_ODDS"
        primary = "B_odds"
    elif model_ceiling and not wc_odds_helped:
        recommendation = "MODEL_LIMITED"
        primary = "A_model"
    elif uefa_ml_top3 >= 0.65 and uefa_cov < 0.01:
        recommendation = "EXPAND_UEFA_GOALSCORER_ODDS"
        primary = "B_odds"
    else:
        recommendation = "BOTH_LIMITED"
        primary = "C_both"

    return {
        "primary_limitation": primary,
        "recommendation": recommendation,
        "evidence": {
            "uefa_odds_coverage_pct": uefa_cov,
            "wc_top3_with_odds": wc_top3,
            "uefa_top3_without_odds": uefa_top3,
            "uefa_ml_top3": uefa_ml_top3,
            "wc_measured_odds_lift_top3": odds_lift,
            "counterfactual_would_reach_70": would_reach_70,
            "gap_wc_vs_uefa_top3": round(wc_top3 - uefa_top3, 4),
        },
    }
