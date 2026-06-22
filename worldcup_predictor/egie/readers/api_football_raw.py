"""Read normalized slices from EGIE PostgreSQL raw store (DB-only, no HTTP)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.egie.config import PROVIDER_API_FOOTBALL
from worldcup_predictor.egie.storage.repository import EgieRawStoreRepository
from worldcup_predictor.outcomes.event_parser import parse_api_football_goal_events
from worldcup_predictor.outcomes.models import GoalEvent


def _unwrap_response(payload: Any) -> Any:
    if isinstance(payload, dict) and "response" in payload:
        return payload.get("response")
    return payload


def load_fixture_item_from_egie(
    fixture_id: int,
    *,
    competition_key: str | None = None,
    season: int | None = None,
    store: EgieRawStoreRepository | None = None,
) -> dict[str, Any] | None:
    repo = store or EgieRawStoreRepository()
    row = repo.get_latest_raw(
        provider=PROVIDER_API_FOOTBALL,
        resource_type="fixtures",
        fixture_id=int(fixture_id),
        competition_key=competition_key,
        season=season,
    )
    if not row:
        return None
    payload = _unwrap_response(row.get("payload_json"))
    if isinstance(payload, list) and payload:
        item = payload[0]
        return item if isinstance(item, dict) else None
    return payload if isinstance(payload, dict) else None


def load_goal_events_from_egie(
    fixture_id: int,
    *,
    home_team: str,
    away_team: str,
    store: EgieRawStoreRepository | None = None,
) -> list[GoalEvent]:
    repo = store or EgieRawStoreRepository()
    row = repo.get_latest_raw(
        provider=PROVIDER_API_FOOTBALL,
        resource_type="events",
        fixture_id=int(fixture_id),
    )
    if not row:
        return []
    raw_events = _unwrap_response(row.get("payload_json"))
    if not isinstance(raw_events, list):
        return []
    return parse_api_football_goal_events(raw_events, home_team=home_team, away_team=away_team)
