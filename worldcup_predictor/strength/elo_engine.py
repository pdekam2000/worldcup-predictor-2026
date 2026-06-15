"""ELO-style rating engine — Phase 44 (API-Football recent fixtures only)."""

from __future__ import annotations

import math
from typing import Any

BASE_ELO = 1500.0
_HOME_ADVANTAGE_ELO = 65.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _league_importance(league: dict[str, Any] | None) -> float:
    if not league:
        return 1.0
    name = str(league.get("name") or "").lower()
    league_type = str(league.get("type") or "").lower()
    if "world cup" in name or "euro" in name or "copa" in name or "nations league" in name:
        return 1.35
    if league_type == "cup":
        return 1.2
    if league_type == "league":
        return 1.1
    if "friendly" in name:
        return 0.85
    return 1.0


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / 400.0))


def _actual_score(home_g: int, away_g: int, team_was_home: bool) -> float:
    if team_was_home:
        if home_g > away_g:
            return 1.0
        if home_g < away_g:
            return 0.0
        return 0.5
    if away_g > home_g:
        return 1.0
    if away_g < home_g:
        return 0.0
    return 0.5


def _goal_diff_multiplier(goal_diff: int) -> float:
    gd = abs(goal_diff)
    if gd <= 1:
        return 1.0
    return min(1.0 + math.log1p(gd) * 0.35, 1.75)


def _parse_match(item: dict[str, Any], team_id: int) -> dict[str, Any] | None:
    goals = item.get("goals") or {}
    teams = item.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    home_id = home.get("id")
    away_id = away.get("id")
    home_g = goals.get("home")
    away_g = goals.get("away")
    if home_g is None or away_g is None:
        return None
    try:
        home_g = int(home_g)
        away_g = int(away_g)
    except (TypeError, ValueError):
        return None
    if team_id == home_id:
        team_was_home = True
    elif team_id == away_id:
        team_was_home = False
    else:
        return None
    return {
        "home_g": home_g,
        "away_g": away_g,
        "team_was_home": team_was_home,
        "league": item.get("league") or {},
        "fixture": item.get("fixture") or {},
    }


def compute_elo_from_fixtures(
    recent_fixtures: list[dict[str, Any]] | None,
    team_id: int | None,
    *,
    base_rating: float = BASE_ELO,
) -> tuple[float, int]:
    """Return (elo_rating, processed_match_count)."""
    if not recent_fixtures or team_id is None:
        return base_rating, 0

    parsed: list[dict[str, Any]] = []
    for item in recent_fixtures:
        match = _parse_match(item, int(team_id))
        if match:
            parsed.append(match)

    if not parsed:
        return base_rating, 0

    # API returns newest first — process oldest to newest for ELO chain.
    parsed.reverse()
    rating = base_rating
    opponent_rating = base_rating

    for match in parsed:
        home_g = match["home_g"]
        away_g = match["away_g"]
        team_was_home = match["team_was_home"]
        importance = _league_importance(match.get("league"))
        k_base = 32.0 * importance

        team_rating = rating + (_HOME_ADVANTAGE_ELO if team_was_home else 0.0)
        opp_rating = opponent_rating + (_HOME_ADVANTAGE_ELO if not team_was_home else 0.0)
        expected = _expected_score(team_rating, opp_rating)
        actual = _actual_score(home_g, away_g, team_was_home)
        gd = home_g - away_g if team_was_home else away_g - home_g
        mult = _goal_diff_multiplier(gd)
        delta = k_base * mult * (actual - expected)
        rating = _clamp(rating + delta, 1200.0, 2200.0)

    return round(rating, 1), len(parsed)
