"""Match schedule endpoints — thin wrappers over existing schedule services."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query

from worldcup_predictor.config.competitions import DEFAULT_COMPETITION_KEY, get_competition
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.api.display_helpers import fixture_to_match_display
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.schedule.competition_schedule import build_schedule_service
from worldcup_predictor.schedule.match_center import build_match_center, classify_status
from worldcup_predictor.quota.fixtures_list_cache import get_cached as get_fixtures_list_cached
from worldcup_predictor.quota.fixtures_list_cache import store as store_fixtures_list_cache
from worldcup_predictor.database.repository import FootballIntelligenceRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/matches", tags=["matches"])

MatchStatusFilter = Literal["upcoming", "live", "finished", "all", "predicted"]


def _is_real_fixture(fixture: TournamentFixture) -> bool:
    return not fixture.is_placeholder and fixture.source != "placeholder"


def _predicted_fixture_ids(settings, competition_key: str) -> set[int]:
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    rows = repo.list_worldcup_stored_predictions(
        competition_key=competition_key,
        limit=500,
        offset=0,
        include_quarantined=False,
    )
    return {int(r["fixture_id"]) for r in rows if r.get("fixture_id") is not None}


def _filter_team(fixtures: list[TournamentFixture], team: str | None) -> list[TournamentFixture]:
    if not team or not team.strip():
        return fixtures
    needle = team.strip().lower()
    return [
        f
        for f in fixtures
        if needle in f.home_team.lower() or needle in f.away_team.lower()
    ]


def _bucket_fixtures(
    fixtures: list[TournamentFixture],
    *,
    status: MatchStatusFilter,
    predicted_ids: set[int],
) -> list[TournamentFixture]:
    if status == "predicted":
        return [f for f in fixtures if f.fixture_id in predicted_ids]

    buckets: dict[str, list[TournamentFixture]] = {"upcoming": [], "live": [], "finished": []}
    for fixture in fixtures:
        bucket = classify_status(fixture.status)
        buckets[bucket].append(fixture)

    if status == "all":
        combined = buckets["live"] + buckets["upcoming"] + buckets["finished"]
        combined.sort(key=lambda f: f.kickoff_time, reverse=True)
        return combined
    if status == "upcoming":
        out = buckets["upcoming"]
        out.sort(key=lambda f: f.kickoff_time)
        return out
    if status == "live":
        out = buckets["live"]
        out.sort(key=lambda f: f.kickoff_time)
        return out
    out = buckets["finished"]
    out.sort(key=lambda f: f.kickoff_time, reverse=True)
    return out


@router.get("")
def list_matches(
    status: MatchStatusFilter = Query(default="upcoming", description="Fixture bucket filter"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    team: str | None = Query(default=None, description="Filter by team name substring"),
    competition: str = Query(default=DEFAULT_COMPETITION_KEY),
    season: int | None = Query(default=None),
    has_prediction: bool | None = Query(default=None, description="Only fixtures with stored predictions"),
) -> dict[str, Any]:
    """Paginated match listing — upcoming, live, finished, all, or predicted fixtures."""
    try:
        comp = get_competition(competition)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if season is not None:
        comp = replace(comp, season=season)

    settings = get_settings()
    try:
        service = build_schedule_service(
            settings,
            competition_key=comp.key,
            season=comp.season,
        )
        snapshot = build_match_center(service, settings, enrich_live=False, enrich_finished_limit=0)
        fixtures = snapshot.upcoming + snapshot.live + snapshot.finished
        fixtures = [f for f in fixtures if _is_real_fixture(f)]
    except Exception as exc:
        logger.exception("Match list API error")
        raise HTTPException(status_code=500, detail="Failed to load matches.") from exc

    predicted_ids = _predicted_fixture_ids(settings, comp.key)
    filtered = _bucket_fixtures(fixtures, status=status, predicted_ids=predicted_ids)
    filtered = _filter_team(filtered, team)
    if has_prediction is True:
        filtered = [f for f in filtered if f.fixture_id in predicted_ids]
    elif has_prediction is False:
        filtered = [f for f in filtered if f.fixture_id not in predicted_ids]

    total_count = len(filtered)
    start = (page - 1) * page_size
    page_rows = filtered[start : start + page_size]

    matches = [
        {
            **fixture_to_match_display(fixture, league=comp.display_name, season=comp.season),
            "has_prediction": fixture.fixture_id in predicted_ids,
            "bucket": classify_status(fixture.status),
        }
        for fixture in page_rows
    ]

    return {
        "status": "ok",
        "competition": comp.key,
        "season": comp.season,
        "filter_status": status,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total_count + page_size - 1) // page_size) if total_count else 0,
        "count": len(matches),
        "matches": matches,
        "predicted_fixture_count": len(predicted_ids),
        "source_label": snapshot.source_label,
    }


@router.get("/upcoming")
def upcoming_matches(
    competition: str = Query(default=DEFAULT_COMPETITION_KEY, description="Competition registry key"),
    season: int | None = Query(default=None, description="Season year override"),
    limit: int = Query(default=0, ge=0, le=200, description="Max fixtures (0 = use app default)"),
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
        fixture_to_match_display(fixture, league=comp.display_name, season=comp.season)
        for fixture in real_fixtures
    ]

    response = {
        "status": "ok",
        "count": len(matches),
        "total_count": len(matches),
        "matches": matches,
        "cache_source": "live",
    }
    store_fixtures_list_cache(comp.key, comp.season, effective_limit, response, settings=settings)
    return response
