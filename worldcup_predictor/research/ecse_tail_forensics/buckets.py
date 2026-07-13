"""Score bucket and outcome classification for tail forensics."""

from __future__ import annotations

from worldcup_predictor.research.ecse_rerank.features import is_btts, is_clean_sheet, parse_scoreline, winner_side
from worldcup_predictor.research.ecse_tail_forensics.constants import (
    HIGH_SCORE_TAIL_LINES,
    LOW_SCORE_LINES,
    MEDIUM_SCORE_LINES,
)


def score_bucket(line: str) -> str:
    if line in LOW_SCORE_LINES:
        return "LOW_SCORE"
    if line in MEDIUM_SCORE_LINES:
        return "MEDIUM_SCORE"
    parsed = parse_scoreline(line)
    if parsed and (parsed[0] + parsed[1] >= 5 or max(parsed) >= 4):
        return "HIGH_SCORE_TAIL"
    if line in HIGH_SCORE_TAIL_LINES:
        return "HIGH_SCORE_TAIL"
    return "MEDIUM_SCORE"


def total_goals_bucket(total: int) -> str:
    if total >= 6:
        return "6_plus"
    return str(total)


def team_goals_bucket(goals: int) -> str:
    if goals >= 4:
        return "4_plus"
    return str(goals)


def classify_fixture_outcomes(
    *,
    actual_score: str,
    home_goals: int,
    away_goals: int,
    odds_home: float,
    odds_away: float,
    lambda_home: float,
    lambda_away: float,
) -> dict[str, bool | str]:
    fav_home = odds_home <= odds_away
    fav_odds = min(odds_home, odds_away)
    underdog_scored = (away_goals > 0 if fav_home else home_goals > 0)
    underdog_two_plus = (away_goals >= 2 if fav_home else home_goals >= 2)
    fav_concedes_one = (away_goals == 1 if fav_home else home_goals == 1)
    fav_concedes_two_plus = (away_goals >= 2 if fav_home else home_goals >= 2)
    er = winner_side(actual_score) or "draw"

    return {
        "score_bucket": score_bucket(actual_score),
        "clean_sheet_home_actual": away_goals == 0,
        "clean_sheet_away_actual": home_goals == 0,
        "btts_yes": is_btts(actual_score),
        "btts_no": not is_btts(actual_score),
        "favourite_concedes_one": fav_concedes_one,
        "favourite_concedes_two_plus": fav_concedes_two_plus,
        "underdog_scores": underdog_scored,
        "underdog_scores_two_plus": underdog_two_plus,
        "draw": er == "draw",
        "home_win": er == "home_win",
        "away_win": er == "away_win",
        "favourite_odds": fav_odds,
        "favourite_is_home": fav_home,
        "lambda_gap": abs(lambda_home - lambda_away),
    }


def top5_diagnostics(top5: list[str]) -> dict[str, int]:
    cs = sum(1 for s in top5 if is_clean_sheet(s))
    btts = sum(1 for s in top5 if is_btts(s))
    return {"top5_clean_sheet_count": cs, "top5_btts_count": btts}
