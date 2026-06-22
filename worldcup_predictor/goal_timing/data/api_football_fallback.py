"""API-Football fallback for missing goal events (quota-safe).

External API calls are restricted to EGIE ingest jobs only.
Feature building and backtests must use SQLite + EGIE PostgreSQL raw store.
"""

from __future__ import annotations

import logging
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.guards import external_api_allowed
from worldcup_predictor.egie.readers.api_football_raw import (
    load_fixture_item_from_egie,
    load_goal_events_from_egie,
)
from worldcup_predictor.goal_timing.data.fixture_ids import is_valid_fixture_id
from worldcup_predictor.goal_timing.leagues import is_goal_timing_allowed_league
from worldcup_predictor.outcomes.event_parser import parse_api_football_goal_events
from worldcup_predictor.outcomes.models import GoalEvent

logger = logging.getLogger(__name__)


class ApiFootballGoalTimingFallback:
    """Reads stored goal events; live API only inside EGIE ingest context."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = ApiFootballClient(self._settings)
        self._repo = FootballIntelligenceRepository(self._settings.sqlite_path or None)
        self.api_calls_made = 0

    def ensure_goal_events(
        self,
        fixture_id: int,
        *,
        home_team: str,
        away_team: str,
        competition_key: str,
        persist: bool = True,
    ) -> tuple[list[GoalEvent], str]:
        if not is_valid_fixture_id(fixture_id):
            logger.info("invalid_fixture_id_skipped fixture_id=%r context=ensure_goal_events", fixture_id)
            return [], "unavailable"

        stored_rows = self._repo.list_fixture_goal_events(int(fixture_id))
        if stored_rows:
            return [GoalEvent.from_row(r) for r in stored_rows], "stored"

        egie_events = load_goal_events_from_egie(
            int(fixture_id),
            home_team=home_team,
            away_team=away_team,
        )
        if egie_events:
            if persist:
                try:
                    self._repo.replace_fixture_goal_events(int(fixture_id), egie_events)
                except Exception:
                    logger.exception("Failed to mirror EGIE goal events into SQLite for fixture %s", fixture_id)
            return egie_events, "egie_postgres"

        if not is_goal_timing_allowed_league(competition_key):
            return [], "unavailable"

        if not external_api_allowed(operation="goal_timing.ensure_goal_events"):
            return [], "unavailable"

        if not self._settings.api_football_configured:
            return [], "unavailable"

        result = self._client.get_fixture_events(int(fixture_id))
        if result.source not in {"live", "cache"}:
            return [], "unavailable"

        self.api_calls_made += 1 if result.source == "live" else 0
        raw_events = result.data if isinstance(result.data, list) else []
        parsed = parse_api_football_goal_events(
            raw_events,
            home_team=home_team,
            away_team=away_team,
        )
        if persist and parsed:
            try:
                self._repo.replace_fixture_goal_events(int(fixture_id), parsed)
            except Exception:
                logger.exception("Failed to persist API-Football goal events for fixture %s", fixture_id)
        return parsed, "api_football" if parsed else "unavailable"

    def get_fixture_metadata(self, fixture_id: int) -> dict[str, Any] | None:
        if not is_valid_fixture_id(fixture_id):
            logger.info("invalid_fixture_id_skipped fixture_id=%r context=get_fixture_metadata", fixture_id)
            return None

        egie_item = load_fixture_item_from_egie(int(fixture_id))
        if egie_item:
            return egie_item

        if not external_api_allowed(operation="goal_timing.get_fixture_metadata"):
            return None

        if not self._settings.api_football_configured:
            return None
        result = self._client.get_fixture_by_id(int(fixture_id))
        items = result.data if isinstance(result.data, list) else []
        if not items:
            return None
        item = items[0] if isinstance(items[0], dict) else None
        return item
