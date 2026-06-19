"""Match schedule endpoints — thin wrappers over existing schedule services."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from worldcup_predictor.config.competitions import DEFAULT_COMPETITION_KEY, get_competition
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.schedule.competition_schedule import build_schedule_service
from worldcup_predictor.quota.fixtures_list_cache import get_cached as get_fixtures_list_cached
from worldcup_predictor.quota.fixtures_list_cache import store as store_fixtures_list_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/matches", tags=["matches"])


def _fixture_to_match_dict(fixture: TournamentFixture, *, league: str, season: int) -> dict[str, Any]:
    return {
        "fixture_id": fixture.fixture_id,
        "date": fixture.kickoff_time.isoformat(),
        "league": league,
        "season": season,
        "home_team": fixture.home_team,
        "away_team": fixture.away_team,
        "status": fixture.status or "NS",
    }


def _is_real_fixture(fixture: TournamentFixture) -> bool:
    return not fixture.is_placeholder and fixture.source != "placeholder"


@router.get("/upcoming")
def upcoming_matches(
    competition: str = Query(default=DEFAULT_COMPETITION_KEY, description="Competition registry key"),
    season: int | None = Query(default=None, description="Season year override"),
    limit: int = Query(default=0, ge=0, le=100, description="Max fixtures (0 = use app default)"),
) -> dict[str, Any]:
    """
    Return upcoming fixtures for a competition.

    Wraps ``build_schedule_service`` + ``WorldCupScheduleService.get_upcoming_matches``
    (same path as ``python main.py schedule`` / CLI ``run_schedule_command``).
    Placeholder/demo fixtures are excluded.
    """
    try:
        comp = get_competition(competition)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if season is not None:
        comp = replace(comp, season=season)

    settings = get_settings()
    effective_limit = limit if limit > 0 else settings.upcoming_fixture_limit

    cached = get_fixtures_list_cached(comp.key, comp.season, effective_limit, settings=settings)
    if cached is not None:
        return cached

    try:
        service = build_schedule_service(
            settings,
            competition_key=comp.key,
            season=comp.season,
        )
        fixtures = service.get_upcoming_matches(limit=effective_limit)
    except RuntimeError as exc:
        logger.warning("Upcoming matches API error (runtime): %s", exc)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "count": 0,
                "matches": [],
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        logger.exception("Upcoming matches API error")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "count": 0,
                "matches": [],
                "message": "Failed to load upcoming matches.",
            },
        ) from exc

    real_fixtures = [fixture for fixture in fixtures if _is_real_fixture(fixture)]
    matches = [
        _fixture_to_match_dict(fixture, league=comp.display_name, season=comp.season)
        for fixture in real_fixtures
    ]

    response = {
        "status": "ok",
        "count": len(matches),
        "matches": matches,
        "cache_source": "live",
    }
    store_fixtures_list_cache(comp.key, comp.season, effective_limit, response, settings=settings)
    return response
