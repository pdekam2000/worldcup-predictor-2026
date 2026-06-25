"""Team name resolution across API-Football and Sportmonks."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.providers.sportmonks_fixture_lookup import _normalize_name, team_names_match


def resolve_team_context(
    *,
    home_team: str,
    away_team: str,
    home_team_id: int | None = None,
    away_team_id: int | None = None,
    league: str | None = None,
    season: int | None = None,
    match_date: str | None = None,
) -> dict[str, Any]:
    return {
        "home_team": home_team,
        "away_team": away_team,
        "home_team_normalized": _normalize_name(home_team),
        "away_team_normalized": _normalize_name(away_team),
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "league": league,
        "season": season,
        "match_date": (match_date or "")[:10] or None,
    }


def teams_match_fixture(
    *,
    home_team: str,
    away_team: str,
    candidate_home: str | None,
    candidate_away: str | None,
) -> bool:
    if not candidate_home or not candidate_away:
        return False
    return team_names_match(home_team, candidate_home) and team_names_match(away_team, candidate_away)


def side_for_market(market_name: str) -> str | None:
    """Return home/away for team-scoped API-Football goalscorer markets."""
    low = (market_name or "").lower().strip()
    if low.startswith("home "):
        return "home"
    if low.startswith("away "):
        return "away"
    return None
