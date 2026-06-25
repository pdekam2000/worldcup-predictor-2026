"""Generalization stress tests — league splits, robustness, tier reliability."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss

from worldcup_predictor.egie.goalscorer_intelligence.confidence_engine import assign_confidence_tiers
from worldcup_predictor.egie.goalscorer_intelligence.feature_pipeline import attach_ml_scores, enrich_intelligence_features
from worldcup_predictor.egie.goalscorer_intelligence.generalization_models import (
    LEAGUE_LABELS,
    LeagueMetrics,
    RobustnessResult,
    TierReliability,
)
from worldcup_predictor.egie.goalscorer_intelligence.ranking_engine import add_ranks
from worldcup_predictor.egie.goalscorer_intelligence.validation import fixture_ranking_hits
from worldcup_predictor.egie.goalscorer_ml_shadow.calibration import expected_calibration_error


def prepare_intelligence_frame(df: pd.DataFrame) -> pd.DataFrame:
    scored = attach_ml_scores(df)
    enriched = enrich_intelligence_features(scored)
    ranked = add_ranks(enriched)
    return assign_confidence_tiers(ranked)


def _recompute_composite(df: pd.DataFrame, *, drop: set[str] | None = None) -> pd.Series:
    drop = drop or set()
    w = {
        "ml_score": 0.35 if "ml" not in drop else 0.0,
        "odds_implied": 0.25 if "odds" not in drop else 0.0,
        "starter_probability": 0.15 if "lineup" not in drop else 0.0,
        "recent_form": 0.10 if "form" not in drop else 0.0,
        "xg_per_90": 0.08 if "xg" not in drop else 0.0,
        "shots_on_target": 0.07 if "sot" not in drop else 0.0,
    }
    total_w = sum(w.values()) or 1.0
    score = (
        (w["ml_score"] / total_w) * df["ml_norm"]
        + (w["odds_implied"] / total_w) * df["odds_norm"]
        + (w["starter_probability"] / total_w) * df["starter_probability"].clip(0, 1)
        + (w["recent_form"] / total_w) * df["form_norm"]
        + (w["xg_per_90"] / total_w) * df["xg_norm"]
        + (w["shots_on_target"] / total_w) * df["sot_norm"]
    )
    return score.round(6)


def league_split_validation(df: pd.DataFrame) -> dict[str, Any]:
    results: dict[str, LeagueMetrics] = {}
    for lid, grp in df.groupby("league_id"):
        label = LEAGUE_LABELS.get(int(lid), f"league_{lid}")
        hits = fixture_ranking_hits(grp, score_col="composite_scorer_score", target_col="target_anytime")
        results[label] = LeagueMetrics(
            league=label,
            league_id=int(lid),
            fixtures=int(grp["sportmonks_fixture_id"].nunique()),
            fixtures_evaluated=hits.fixtures_evaluated,
            top1_hit=hits.top1_hit,
            top3_hit=hits.top3_hit,
            top5_hit=hits.top5_hit,
        )
    return {k: v.to_dict() for k, v in results.items()}


def confidence_stability(df: pd.DataFrame) -> dict[str, Any]:
    tier_metrics: dict[str, dict[str, Any]] = {}
    top3_by_tier: dict[str, float] = {}

    for tier, grp in df.groupby("confidence_tier"):
        hits = fixture_ranking_hits(grp, score_col="composite_scorer_score", target_col="target_anytime")
        tier_metrics[str(tier)] = hits.to_dict()
        top3_by_tier[str(tier)] = hits.top3_hit

    ordering = ["A", "B", "C", "D"]
    present = [t for t in ordering if t in top3_by_tier]
    monotonic = all(
        top3_by_tier.get(present[i], 0) >= top3_by_tier.get(present[i + 1], 0)
        for i in range(len(present) - 1)
    )
    tier_a_superior = top3_by_tier.get("A", 0) >= max(top3_by_tier.get("B", 0), top3_by_tier.get("C", 0), top3_by_tier.get("D", 0))

    return {
        "tier_metrics": tier_metrics,
        "top3_by_tier": top3_by_tier,
        "monotonic_ordering": monotonic,
        "tier_a_superior": tier_a_superior,
    }


def robustness_audit(df: pd.DataFrame) -> dict[str, Any]:
    baseline = fixture_ranking_hits(df, score_col="composite_scorer_score", target_col="target_anytime")
    base_top3 = baseline.top3_hit

    scenarios = {
        "baseline": set(),
        "no_odds": {"odds"},
        "no_xg": {"xg"},
        "no_lineup": {"lineup"},
        "no_form": {"form"},
        "ml_only": {"odds", "lineup", "form", "xg", "sot"},
    }

    results: list[RobustnessResult] = []
    feature_impact: dict[str, float] = {}

    for name, drop in scenarios.items():
        test = df.copy()
        if name == "baseline":
            col = "composite_scorer_score"
        else:
            test["composite_ablated"] = _recompute_composite(test, drop=drop)
            col = "composite_ablated"
        hits = fixture_ranking_hits(test, score_col=col, target_col="target_anytime")
        drop_val = round(base_top3 - hits.top3_hit, 4) if name != "baseline" else 0.0
        results.append(
            RobustnessResult(
                scenario=name,
                top3_hit=hits.top3_hit,
                top3_drop=drop_val,
                fixtures_evaluated=hits.fixtures_evaluated,
            )
        )
        if name.startswith("no_"):
            feature_impact[name.replace("no_", "")] = drop_val

    ranked_impact = sorted(feature_impact.items(), key=lambda x: x[1], reverse=True)
    return {
        "baseline_top3": base_top3,
        "scenarios": [r.to_dict() for r in results],
        "feature_impact_ranking": ranked_impact,
        "primary_carrier": ranked_impact[0][0] if ranked_impact else "ml",
    }


def tier_reliability(df: pd.DataFrame, *, min_samples: int = 30) -> dict[str, Any]:
    tiers: list[TierReliability] = []
    for tier, grp in df.groupby("confidence_tier"):
        sub = grp.copy()
        n = len(sub)
        fid_n = int(sub["sportmonks_fixture_id"].nunique())
        hit_rate = float(sub["target_anytime"].mean()) if n else 0.0

        brier = ece = None
        if n >= min_samples and sub["composite_scorer_score"].notna().any():
            y = sub["target_anytime"].astype(int).values
            p = np.clip(sub["composite_scorer_score"].astype(float).values, 1e-6, 1 - 1e-6)
            brier = round(float(brier_score_loss(y, p)), 4)
            ece = expected_calibration_error(y, p)

        tiers.append(
            TierReliability(
                tier=str(tier),
                sample_count=n,
                fixture_count=fid_n,
                hit_rate=round(hit_rate, 4),
                brier=brier,
                ece=ece,
            )
        )

    return {
        "tiers": [t.to_dict() for t in tiers],
        "statistically_meaningful": all(t.sample_count >= min_samples for t in tiers if t.tier in ("A", "B")),
    }


def elite_candidate_test(
    overall: dict[str, Any],
    league_results: dict[str, Any],
    confidence: dict[str, Any],
    robustness: dict[str, Any],
    *,
    wc_only_top3: float | None = None,
) -> dict[str, Any]:
    overall_hits = overall.get("composite_scorer") or overall
    if isinstance(overall_hits, dict) and "top3_hit" in overall_hits:
        top3 = float(overall_hits["top3_hit"])
    else:
        top3 = float((overall.get("markets") or {}).get("anytime", {}).get("composite_scorer", {}).get("top3_hit", 0))

    league_top3 = {k: float(v.get("top3_hit", 0)) for k, v in league_results.items()}
    min_league = min(league_top3.values()) if league_top3 else 0.0
    stable_across_leagues = min_league >= 0.55
    tier_monotonic = bool(confidence.get("monotonic_ordering"))
    tier_a_superior = bool(confidence.get("tier_a_superior"))
    top3_pass = top3 >= 0.70

    collapse = False
    if wc_only_top3 is not None:
        collapse = top3 < wc_only_top3 - 0.15

    checks = {
        "top3_gte_70": top3_pass,
        "stable_across_leagues": stable_across_leagues,
        "tier_ordering_preserved": tier_monotonic,
        "tier_a_superior": tier_a_superior,
        "no_major_collapse": not collapse,
    }
    all_pass = all(checks.values())

    if all_pass:
        recommendation = "GOALSCORER_ELITE_CONFIRMED"
    elif top3 >= 0.60 or min_league >= 0.50:
        recommendation = "GOALSCORER_HIGH_VALUE"
    else:
        recommendation = "GOALSCORER_MEDIUM_VALUE"

    return {
        "checks": checks,
        "overall_top3": top3,
        "min_league_top3": min_league,
        "league_top3": league_top3,
        "wc_only_top3": wc_only_top3,
        "recommendation": recommendation,
        "all_pass": all_pass,
    }
