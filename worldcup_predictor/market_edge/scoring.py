"""MARKET_EDGE_SCORE computation and ranking."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.market_edge.models import MarketProfile, ScoredMarket

WEIGHTS = {
    "accuracy_edge": 0.28,
    "calibration": 0.14,
    "coverage": 0.14,
    "stability": 0.14,
    "odds_availability": 0.12,
    "roi_potential": 0.18,
}


def _accuracy_edge(profile: MarketProfile) -> float:
    if profile.accuracy is None:
        return 0.0
    baseline = profile.baseline_accuracy if profile.baseline_accuracy is not None else 0.5
    acc = profile.accuracy
    if profile.accuracy_metric == "top3_hit":
        return max(0.0, min(1.0, (acc - baseline) / max(0.05, 1.0 - baseline)))
    return max(0.0, min(1.0, (acc - baseline) / max(0.05, 1.0 - baseline)))


def _calibration_score(profile: MarketProfile) -> float:
    if profile.calibration_ece is None:
        return 0.45
    return max(0.0, min(1.0, 1.0 - min(profile.calibration_ece, 0.5) * 2))


def _coverage_score(profile: MarketProfile) -> float:
    size = max(0, profile.dataset_size)
    size_score = min(1.0, math.log10(max(1, size)) / 3.2)
    return max(0.0, min(1.0, 0.6 * size_score + 0.4 * profile.coverage_pct))


def score_market(profile: MarketProfile) -> ScoredMarket:
    breakdown = {
        "accuracy_edge": round(_accuracy_edge(profile), 4),
        "calibration": round(_calibration_score(profile), 4),
        "coverage": round(_coverage_score(profile), 4),
        "stability": round(max(0.0, min(1.0, profile.stability_score)), 4),
        "odds_availability": round(max(0.0, min(1.0, profile.odds_availability_pct)), 4),
        "roi_potential": round(max(0.0, min(1.0, profile.roi_potential)), 4),
    }
    edge = 100.0 * sum(WEIGHTS[k] * breakdown[k] for k in WEIGHTS)
    return ScoredMarket(
        market_id=profile.market_id,
        display_name=profile.display_name,
        market_edge_score=round(edge, 2),
        profile=profile,
        score_breakdown=breakdown,
    )


def rank_markets(profiles: dict[str, MarketProfile]) -> list[ScoredMarket]:
    scored = [score_market(p) for p in profiles.values()]
    return sorted(scored, key=lambda m: m.market_edge_score, reverse=True)


def select_candidates(ranked: list[ScoredMarket]) -> dict[str, Any]:
    top10 = ranked[:10]
    research = [
        m
        for m in ranked
        if m.profile.infrastructure_tier in (
            "goalscorer_54k_54s",
            "ml1_labels",
            "goal_timing_xg",
            "goal_timing",
        )
        and m.profile.production_status not in ("production",)
    ][:5]
    if len(research) < 5:
        research = ranked[1:6]

    production = [
        m
        for m in ranked
        if m.profile.production_status in ("production", "production_derived", "shadow_high_value")
    ][:3]
    if len(production) < 3:
        production = ranked[:3]

    return {
        "top10_strongest": [m.to_dict() for m in top10],
        "top5_research_candidates": [m.to_dict() for m in research[:5]],
        "top3_production_candidates": [m.to_dict() for m in production[:3]],
    }


def recommend_dev_hours(ranked: list[ScoredMarket]) -> dict[str, Any]:
    gs = next((m for m in ranked if m.market_id == "anytime_goalscorer"), None)
    fg = next((m for m in ranked if m.market_id == "first_goal_team"), None)
    btts = next((m for m in ranked if m.market_id == "btts"), None)

    if gs and gs.market_edge_score >= (fg.market_edge_score if fg else 0):
        recommendation = "ANYTIME_GOALSCORER_ODDS_EXPANSION"
        rationale = (
            "Highest conditional edge when odds exist (77% WC top-3, 75% disagree hit). "
            "54Q-1 showed UEFA gap is primarily odds coverage; 100h on odds bridge + UEFA expansion "
            "has highest ROI vs team/availability features (54R/54S plateau)."
        )
        target_market = "anytime_goalscorer"
    elif fg and (fg.market_edge_score or 0) >= 55:
        recommendation = "FIRST_GOAL_TEAM_REFINEMENT"
        rationale = "Best balanced production-ready fixture market with xG baseline ~58% and PL live ~51%."
        target_market = "first_goal_team"
    elif btts:
        recommendation = "BTTS_CALIBRATION"
        rationale = "Production market with moderate accuracy; calibration improvement lowest hanging fruit."
        target_market = "btts"
    else:
        recommendation = "MULTI_MARKET_PORTFOLIO"
        rationale = "No single market dominates; spread investment."
        target_market = ranked[0].market_id if ranked else "1x2"

    return {
        "recommendation": recommendation,
        "target_market": target_market,
        "rationale": rationale,
        "allocated_hours": 100,
    }
