"""Prematch feature extraction for tail-risk detection — no postmatch leakage."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.research.ecse_historical_replay.replay_engine import ReplayRow
from worldcup_predictor.research.ecse_lambda_extraction import btts_prob_independent
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution, poisson_pmf
from worldcup_predictor.research.ecse_tail_forensics.buckets import score_bucket
from worldcup_predictor.research.ecse_tail_forensics.distributions import prob_map, tail_diagnostics, topn
from worldcup_predictor.research.eeso.metrics import implied_wde_direction


def is_high_score_tail_label(actual_score: str) -> bool:
    return score_bucket(actual_score) == "HIGH_SCORE_TAIL"


def implied_1x2_probs(oh: float, od: float, oa: float) -> tuple[float, float, float]:
    ph = 1.0 / max(oh, 1.01)
    pd = 1.0 / max(od, 1.01)
    pa = 1.0 / max(oa, 1.01)
    t = ph + pd + pa
    return ph / t, pd / t, pa / t


def implied_over_25_from_lambda(lh: float, la: float) -> float:
    lam = lh + la
    cdf = sum(poisson_pmf(k, lam) for k in range(3))
    return 1.0 - cdf


def distribution_prematch_features(dist: list[dict[str, Any]], *, fav_home: bool) -> dict[str, float | None]:
    pm = prob_map(dist)
    td = tail_diagnostics(dist)
    prob_home_3plus = sum(pm.get(f"{h}-{a}", 0.0) for h in range(8) for a in range(8) if h >= 3)
    prob_away_2plus = sum(pm.get(f"{h}-{a}", 0.0) for h in range(8) for a in range(8) if a >= 2)
    prob_btts = sum(p for k, p in pm.items() if "-" in k and all(int(x) > 0 for x in k.split("-")))
    if fav_home:
        fav_con1 = sum(pm.get(f"{h}-1", 0.0) for h in range(8))
        fav_con2 = sum(pm.get(f"{h}-{a}", 0.0) for h in range(8) for a in range(2, 8))
    else:
        fav_con1 = sum(pm.get(f"1-{a}", 0.0) for a in range(8))
        fav_con2 = sum(pm.get(f"{h}-{a}", 0.0) for h in range(2, 8) for a in range(8))
    return {
        "canonical_high_score_tail_mass": td["high_score_tail_mass"],
        "canonical_btts_mass": td["btts_mass"],
        "prob_home_scores_3plus": round(prob_home_3plus, 6),
        "prob_away_scores_2plus": round(prob_away_2plus, 6),
        "prob_both_teams_score": round(prob_btts, 6),
        "prob_favourite_concedes_one": round(fav_con1, 6),
        "prob_favourite_concedes_two_plus": round(fav_con2, 6),
    }


def last8_prematch_features(home_profile: dict[str, Any] | None, away_profile: dict[str, Any] | None) -> dict[str, float | None]:
    def _rate(profile: dict[str, Any] | None, section: str, key: str, denom_key: str = "matches_found") -> float | None:
        if not profile:
            return None
        n = profile.get("identity", {}).get(denom_key)
        if not n:
            return None
        val = (profile.get(section) or {}).get(key)
        if val is None:
            return None
        return round(float(val) / float(n), 4)

    hg = home_profile or {}
    ag = away_profile or {}
    return {
        "last8_home_avg_scored": (hg.get("goal_output") or {}).get("avg_goals_scored_last8"),
        "last8_home_avg_conceded": (hg.get("goal_output") or {}).get("avg_goals_conceded_last8"),
        "last8_away_avg_scored": (ag.get("goal_output") or {}).get("avg_goals_scored_last8"),
        "last8_away_avg_conceded": (ag.get("goal_output") or {}).get("avg_goals_conceded_last8"),
        "last8_home_scored_in_rate": _rate(hg, "goal_output", "scored_in_match_count"),
        "last8_away_scored_in_rate": _rate(ag, "goal_output", "scored_in_match_count"),
        "last8_home_btts_rate": _rate(hg, "market_shape", "BTTS_yes_count"),
        "last8_away_btts_rate": _rate(ag, "market_shape", "BTTS_yes_count"),
        "last8_home_over25_rate": _rate(hg, "market_shape", "over_2_5_count"),
        "last8_away_over25_rate": _rate(ag, "market_shape", "over_2_5_count"),
    }


def build_prematch_feature_row(
    row: ReplayRow,
    *,
    league_priors: dict[str, dict[str, float | None]],
    home_profile: dict[str, Any] | None = None,
    away_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Leakage-safe prematch features. Label stored separately for training."""
    dist = generate_score_distribution(row.lambda_home, row.lambda_away)
    fav_home = row.odds_home <= row.odds_away
    ph, pd, pa = implied_1x2_probs(row.odds_home, row.odds_draw, row.odds_away)
    dist_feats = distribution_prematch_features(dist, fav_home=fav_home)
    l8 = last8_prematch_features(home_profile, away_profile)
    priors = league_priors.get(row.league or "unknown", {})
    model_btts = btts_prob_independent(row.lambda_home, row.lambda_away)

    features: dict[str, Any] = {
        "fixture_id": row.fixture_key,
        "league": row.league,
        "season": row.season,
        "kickoff": row.kickoff,
        "event_date": row.event_date,
        "match": row.match,
        "lambda_home": row.lambda_home,
        "lambda_away": row.lambda_away,
        "total_lambda": row.lambda_total,
        "lambda_gap": abs(row.lambda_home - row.lambda_away),
        "entropy": row.entropy,
        "top3_mass": row.top3_mass,
        "top5_mass": row.top5_mass,
        "implied_over_25": round(implied_over_25_from_lambda(row.lambda_home, row.lambda_away), 4),
        "implied_btts_yes": round(model_btts, 4),
        "odds_home": row.odds_home,
        "odds_draw": row.odds_draw,
        "odds_away": row.odds_away,
        "favourite_odds": min(row.odds_home, row.odds_away),
        "wde_home_prob": round(ph, 4),
        "wde_draw_prob": round(pd, 4),
        "wde_away_prob": round(pa, 4),
        "wde_direction": implied_wde_direction(row.odds_home, row.odds_draw, row.odds_away),
        "league_avg_goals": priors.get("league_avg_goals"),
        "league_btts_rate": priors.get("league_btts_rate"),
        "league_high_tail_rate": priors.get("league_high_tail_rate"),
        **dist_feats,
        **l8,
        "xg": None,
        "pressure": None,
        "lineup_strength": None,
        "injuries": None,
    }
    return features


def compute_league_priors_from_labels(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    """Train-set-only league statistics."""
    from collections import defaultdict

    totals: dict[str, list[float]] = defaultdict(list)
    btts: dict[str, list[int]] = defaultdict(list)
    tail: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        lg = r.get("league") or "unknown"
        totals[lg].append(float(r.get("actual_total_goals") or 0))
        btts[lg].append(1 if r.get("label_btts") else 0)
        tail[lg].append(1 if r.get("label_high_score_tail") else 0)
    out: dict[str, dict[str, float | None]] = {}
    for lg, vals in totals.items():
        n = len(vals)
        out[lg] = {
            "league_avg_goals": round(sum(vals) / n, 4) if n else None,
            "league_btts_rate": round(sum(btts[lg]) / n, 4) if n else None,
            "league_high_tail_rate": round(sum(tail[lg]) / n, 4) if n else None,
        }
    return out


def feature_vector(row: dict[str, Any], columns: tuple[str, ...]) -> list[float | None]:
    return [row.get(c) for c in columns]
