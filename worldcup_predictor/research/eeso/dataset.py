"""Leakage-safe EESO research dataset row builder."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_historical_replay.replay_engine import ReplayRow
from worldcup_predictor.research.ecse_rerank.features import is_btts
from worldcup_predictor.research.eeso.metrics import actual_end_result, implied_wde_direction


def _btts_result(home: int, away: int) -> str:
    return "yes" if home > 0 and away > 0 else "no"


def _ou_result(home: int, away: int) -> str:
    return "over_2_5" if home + away > 2 else "under_2_5"


def build_fixture_dataset_row(
    row: ReplayRow,
    *,
    home_profile: dict[str, Any],
    away_profile: dict[str, Any],
    full_distribution: list[dict[str, Any]],
    wde_direction: str,
) -> dict[str, Any]:
    """Assemble one leakage-safe research record with explicit missing fields."""
    actual_er = actual_end_result(row.actual_home, row.actual_away)
    return {
        "identity": {
            "fixture_id": row.fixture_key,
            "league": row.league,
            "country": None,
            "season": row.season,
            "kickoff": row.kickoff,
            "home_team": row.match.split(" vs ")[0].strip(),
            "away_team": row.match.split(" vs ")[-1].strip(),
            "competition": row.competition,
            "stage": row.stage,
        },
        "canonical_ecse": {
            "score_distribution": full_distribution[:15] if full_distribution else None,
            "top1": row.top1,
            "top3": [x["scoreline"] for x in row.top10[:3]],
            "top5": row.top5,
            "top10": [x["scoreline"] for x in row.top10],
            "top3_mass": row.top3_mass,
            "top5_mass": row.top5_mass,
            "entropy": row.entropy,
            "lambda_home": row.lambda_home,
            "lambda_away": row.lambda_away,
            "total_lambda": row.lambda_total,
            "actual_rank": row.actual_rank,
        },
        "wde": {
            "wde_decision": wde_direction,
            "ft_marginal_direction": wde_direction,
            "h_prob": round(1.0 / max(row.odds_home, 1.01), 4),
            "d_prob": round(1.0 / max(row.odds_draw, 1.01), 4),
            "a_prob": round(1.0 / max(row.odds_away, 1.01), 4),
            "wde_confidence": None,
            "execution_status": "replay_implied_odds",
        },
        "markets": {
            "btts": None,
            "ou_2_5": None,
            "prematch_odds": {
                "home": row.odds_home,
                "draw": row.odds_draw,
                "away": row.odds_away,
            },
            "odds_timestamp": None,
            "odds_freshness": None,
            "odds_movement": None,
        },
        "last8": {
            "home": _profile_slice(home_profile),
            "away": _profile_slice(away_profile),
        },
        "optional_advanced": {
            "xg": None,
            "pressure": None,
            "lineup_strength": None,
            "injury_impact": None,
            "calibration_bucket": None,
            "league_reliability": None,
        },
        "ground_truth": {
            "regulation_final_score": row.actual_score,
            "end_result": actual_er,
            "btts_result": _btts_result(row.actual_home, row.actual_away),
            "ou_result": _ou_result(row.actual_home, row.actual_away),
            "actual_ecse_rank": row.actual_rank,
        },
    }


def _profile_slice(profile: dict[str, Any]) -> dict[str, Any]:
    identity = profile.get("identity") or {}
    goals = profile.get("goal_output") or {}
    defense = profile.get("defensive_output") or {}
    market = profile.get("market_shape") or {}
    venue = profile.get("venue_split") or {}
    opp = profile.get("opponent_quality") or {}
    return {
        "goals_scored": goals.get("total_goals_scored_last8"),
        "goals_conceded": goals.get("total_goals_conceded_last8"),
        "average_scored": goals.get("avg_goals_scored_last8"),
        "average_conceded": goals.get("avg_goals_conceded_last8"),
        "clean_sheets": defense.get("clean_sheets_count"),
        "scored_in_x_matches": goals.get("scored_in_match_count"),
        "btts_frequency": market.get("BTTS_yes_count"),
        "over_2_5_frequency": market.get("over_2_5_count"),
        "home_away_split": venue,
        "opponent_strength": opp.get("annotated") if opp.get("annotated") else None,
        "coverage_status": identity.get("coverage_status"),
        "matches_found": identity.get("matches_found"),
    }


def wde_direction_for_row(row: ReplayRow) -> str:
    return implied_wde_direction(row.odds_home, row.odds_draw, row.odds_away)
