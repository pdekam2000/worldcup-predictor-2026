"""Competition registry API — dynamic league list for Match Center."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Query

from worldcup_predictor.api.match_center_helpers import (
    competition_to_api_dict,
    list_enabled_competitions,
)
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.quota.match_schedule_cache import get_schedule_cache
from worldcup_predictor.schedule.competition_schedule import build_schedule_service
from worldcup_predictor.schedule.match_center import build_match_center
from worldcup_predictor.schedule.season_resolver import resolve_active_season

router = APIRouter(prefix="/competitions", tags=["competitions"])


def _is_real_fixture(fixture: TournamentFixture) -> bool:
    return not fixture.is_placeholder and fixture.source != "placeholder"


def _upcoming_count(comp_key: str, season: int) -> int:
    settings = get_settings()
    cached = get_schedule_cache(comp_key, season, settings=settings)
    if cached:
        return len([f for f in cached.fixtures if classify_upcoming(f)])
    try:
        service = build_schedule_service(settings, competition_key=comp_key, season=season)
        snapshot = build_match_center(service, settings, enrich_live=False, enrich_finished_limit=0)
        fixtures = [f for f in snapshot.upcoming if _is_real_fixture(f)]
        return len(fixtures)
    except Exception:
        return 0


def classify_upcoming(fixture: TournamentFixture) -> bool:
    from worldcup_predictor.schedule.match_center import classify_status

    return _is_real_fixture(fixture) and classify_status(fixture.status) == "upcoming"


def _classify_zero_fixture_reason(comp_key: str, season: int) -> str | None:
    settings = get_settings()
    cached = get_schedule_cache(comp_key, season, settings=settings)
    if cached and len(cached.fixtures) == 0:
        return "provider_returned_empty"
    try:
        service = build_schedule_service(settings, competition_key=comp_key, season=season)
        snapshot = build_match_center(service, settings, enrich_live=False, enrich_finished_limit=0)
        real = [f for f in snapshot.upcoming + snapshot.live + snapshot.finished if _is_real_fixture(f)]
        if not real:
            return "off_season_or_provider_empty"
        upcoming = [f for f in snapshot.upcoming if classify_upcoming(f)]
        if not upcoming:
            return "no_upcoming_in_window"
    except Exception as exc:
        msg = str(exc).lower()
        if "quota" in msg or "plan" in msg or "subscription" in msg:
            return "provider_plan_coverage"
        return "api_error"
    return None


@router.get("")
def list_competitions(
    include_counts: bool = Query(default=True, description="Include upcoming fixture counts"),
) -> dict[str, Any]:
    """Return all enabled competitions with auto-resolved active seasons."""
    settings = get_settings()
    comps = list_enabled_competitions()
    items: list[dict[str, Any]] = []
    total_upcoming = 0
    for comp in comps:
        resolved_season = resolve_active_season(comp.key, settings=settings)
        comp = replace(comp, season=resolved_season)
        count = _upcoming_count(comp.key, comp.season) if include_counts else 0
        total_upcoming += count
        row = competition_to_api_dict(comp, upcoming_count=count)
        row["resolved_season"] = resolved_season
        row["provider_league_id"] = comp.league_id
        if count == 0 and include_counts:
            row["zero_fixture_reason"] = _classify_zero_fixture_reason(comp.key, resolved_season)
        items.append(row)

    items.sort(key=lambda c: (-int(c.get("upcoming_count") or 0), c.get("name") or ""))

    return {
        "status": "ok",
        "count": len(items),
        "total_upcoming": total_upcoming,
        "competitions": items,
    }
