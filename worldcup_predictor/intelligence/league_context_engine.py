"""Phase 39D — League-specific historical context for predictions."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.competition.competition_service import CompetitionService
from worldcup_predictor.config.league_registry import learning_profile_for
from worldcup_predictor.database.repository import FootballIntelligenceRepository


def attach_league_prediction_context(
    context: Any,
    *,
    fixture_id: int,
    home_team: str | None = None,
    away_team: str | None = None,
    repository: FootballIntelligenceRepository | None = None,
) -> dict[str, Any]:
    """Load league form/tendencies into agent context (European leagues only)."""
    comp_key = getattr(context, "competition_key", None) or "world_cup_2026"
    if CompetitionService().is_worldcup_mode(comp_key):
        return {}

    repo = repository or FootballIntelligenceRepository()
    season = context.shared.get("season")
    league_ctx = build_league_context(
        repo,
        competition_key=comp_key,
        home_team=home_team,
        away_team=away_team,
        season=season,
    )
    league_ctx["competition_profile"] = context.shared.get("competition_profile") or learning_profile_for(
        comp_key
    )
    league_ctx["fixture_id"] = fixture_id
    context.shared["league_context"] = league_ctx
    return league_ctx


def build_league_context(
    repo: FootballIntelligenceRepository,
    *,
    competition_key: str,
    home_team: str | None,
    away_team: str | None,
    season: int | None = None,
    recent_limit: int = 8,
) -> dict[str, Any]:
    """Aggregate home/away form, BTTS/O-U tendencies from stored results."""
    ctx: dict[str, Any] = {
        "competition_key": competition_key,
        "season": season,
        "home_form": {},
        "away_form": {},
        "league_tendencies": {},
        "halftime_patterns": {},
        "first_goal_timing": {},
        "player_goal_history": {},
        "odds_available": False,
        "data_gaps": [],
    }

    if home_team:
        ctx["home_form"] = repo.team_form_summary(
            competition_key=competition_key,
            team_name=home_team,
            venue_side="home",
            season=season,
            limit=recent_limit,
        )
    if away_team:
        ctx["away_form"] = repo.team_form_summary(
            competition_key=competition_key,
            team_name=away_team,
            venue_side="away",
            season=season,
            limit=recent_limit,
        )

    ctx["league_tendencies"] = repo.competition_tendencies(
        competition_key=competition_key,
        season=season,
    )
    ctx["halftime_patterns"] = repo.halftime_pattern_summary(
        competition_key=competition_key,
        season=season,
    )
    ctx["first_goal_timing"] = repo.first_goal_timing_summary(
        competition_key=competition_key,
        season=season,
    )

    if home_team and away_team:
        ctx["player_goal_history"] = repo.player_goal_history_for_teams(
            competition_key=competition_key,
            home_team=home_team,
            away_team=away_team,
            season=season,
        )

    if not ctx["home_form"] and home_team:
        ctx["data_gaps"].append("home_form")
    if not ctx["away_form"] and away_team:
        ctx["data_gaps"].append("away_form")
    if not ctx["league_tendencies"]:
        ctx["data_gaps"].append("league_tendencies")

    return ctx
