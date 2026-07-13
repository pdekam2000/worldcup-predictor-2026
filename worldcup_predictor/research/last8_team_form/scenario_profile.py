"""Shadow scenario profile from Last-8 home/away profiles."""

from __future__ import annotations

from typing import Any


def _rate(count: int | None, n: int | None) -> float | None:
    if count is None or not n:
        return None
    return round(count / n, 4)


def build_shadow_scenario_profile(
    *,
    home_profile: dict[str, Any],
    away_profile: dict[str, Any],
    venue_home: bool = True,
) -> dict[str, Any]:
    """Evidence features for shadow Top5 selection — not calibrated final probabilities."""
    hn = int(home_profile.get("identity", {}).get("matches_found") or 0)
    an = int(away_profile.get("identity", {}).get("matches_found") or 0)
    hg = home_profile.get("goal_output") or {}
    hd = home_profile.get("defensive_output") or {}
    hm = home_profile.get("market_shape") or {}
    hv = home_profile.get("venue_split") or {}
    ag = away_profile.get("goal_output") or {}
    ad = away_profile.get("defensive_output") or {}
    am = away_profile.get("market_shape") or {}
    av = away_profile.get("venue_split") or {}

    home_venue_for = hv.get("home_goals_for") if venue_home else hv.get("away_goals_for")
    home_venue_against = hv.get("home_goals_against") if venue_home else hv.get("away_goals_against")
    home_venue_n = hv.get("home_matches_count") if venue_home else hv.get("away_matches_count")

    away_venue_for = av.get("away_goals_for") if venue_home else av.get("home_goals_for")
    away_venue_against = av.get("away_goals_against") if venue_home else av.get("home_goals_against")
    away_venue_n = av.get("away_matches_count") if venue_home else av.get("home_matches_count")

    home_attack = {
        "recent_scoring_rate": hg.get("weighted_avg_goals_scored") or hg.get("avg_goals_scored_last8"),
        "venue_relevant_scoring_rate": round(home_venue_for / home_venue_n, 4) if home_venue_n else None,
        "scoring_consistency": _rate(hg.get("scored_in_match_count"), hn),
        "scored_2plus_frequency": _rate(hg.get("scored_2plus_count"), hn),
        "scored_3plus_frequency": _rate(hg.get("scored_3plus_count"), hn),
    }
    home_defense = {
        "clean_sheet_rate": _rate(hd.get("clean_sheets_count"), hn),
        "conceded_1_frequency": _rate(
            sum(1 for m in home_profile.get("matches", []) if m.get("goals_against") == 1),
            hn,
        ),
        "conceded_2plus_frequency": _rate(hd.get("conceded_2plus_count"), hn),
    }
    away_attack = {
        "recent_scoring_rate": ag.get("weighted_avg_goals_scored") or ag.get("avg_goals_scored_last8"),
        "away_scoring_rate": round(away_venue_for / away_venue_n, 4) if away_venue_n else None,
        "scored_at_least_one_probability_proxy": _rate(ag.get("scored_in_match_count"), an),
        "scored_2plus_frequency": _rate(ag.get("scored_2plus_count"), an),
    }
    away_defense = {
        "clean_sheet_rate": _rate(ad.get("clean_sheets_count"), an),
        "conceded_1_frequency": _rate(
            sum(1 for m in away_profile.get("matches", []) if m.get("goals_against") == 1),
            an,
        ),
        "conceded_2plus_frequency": _rate(ad.get("conceded_2plus_count"), an),
    }

    away_scores_one = away_attack.get("scored_at_least_one_probability_proxy") or 0.0
    home_cs = home_defense.get("clean_sheet_rate") or 0.0
    away_cs = away_defense.get("clean_sheet_rate") or 0.0
    btts_home = _rate(hm.get("BTTS_yes_count"), hn) or 0.0
    btts_away = _rate(am.get("BTTS_yes_count"), an) or 0.0
    over_home = _rate(hm.get("over_2_5_count"), hn) or 0.0
    over_away = _rate(am.get("over_2_5_count"), an) or 0.0

    scenario_risks = {
        "home_clean_sheet_risk": round(1.0 - home_cs, 4) if hn else None,
        "away_clean_sheet_risk": round(1.0 - away_cs, 4) if an else None,
        "opponent_scores_one_risk": round(float(away_scores_one), 4) if an else None,
        "opponent_scores_two_plus_risk": round(float(away_attack.get("scored_2plus_frequency") or 0), 4),
        "draw_score_risk": round(min(btts_home, btts_away), 4),
        "high_score_tail_risk": round((over_home + over_away) / 2.0, 4) if hn and an else None,
    }

    return {
        "shadow_only": True,
        "home_attack_profile": home_attack,
        "home_defense_profile": home_defense,
        "away_attack_profile": away_attack,
        "away_defense_profile": away_defense,
        "scenario_risks": scenario_risks,
        "coverage_quality": {
            "home": home_profile.get("identity", {}).get("coverage_status"),
            "away": away_profile.get("identity", {}).get("coverage_status"),
        },
    }
