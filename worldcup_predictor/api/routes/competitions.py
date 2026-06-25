"""Competition registry API — dynamic league list for Match Center."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from worldcup_predictor.api.match_center_helpers import (
    apply_season_override,
    competition_to_api_dict,
    list_enabled_competitions,
)
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.schedule.competition_schedule import build_schedule_service
from worldcup_predictor.schedule.match_center import build_match_center
from worldcup_predictor.domain.schedule import TournamentFixture

router = APIRouter(prefix="/competitions", tags=["competitions"])


def _is_real_fixture(fixture: TournamentFixture) -> bool:
    return not fixture.is_placeholder and fixture.source != "placeholder"


def _upcoming_count(comp_key: str, season: int) -> int:
    settings = get_settings()
    try:
        service = build_schedule_service(settings, competition_key=comp_key, season=season)
        snapshot = build_match_center(service, settings, enrich_live=False, enrich_finished_limit=0)
        fixtures = [f for f in snapshot.upcoming if _is_real_fixture(f)]
        return len(fixtures)
    except Exception:
        return 0


@router.get("")
def list_competitions(
    include_counts: bool = Query(default=True, description="Include upcoming fixture counts"),
) -> dict[str, Any]:
    """Return all enabled competitions from the purchased API plan registry."""
    comps = list_enabled_competitions()
    items: list[dict[str, Any]] = []
    total_upcoming = 0
    for comp in comps:
        count = _upcoming_count(comp.key, comp.season) if include_counts else 0
        total_upcoming += count
        items.append(competition_to_api_dict(comp, upcoming_count=count))

    items.sort(key=lambda c: (-int(c.get("upcoming_count") or 0), c.get("name") or ""))

    return {
        "status": "ok",
        "count": len(items),
        "total_upcoming": total_upcoming,
        "competitions": items,
    }
