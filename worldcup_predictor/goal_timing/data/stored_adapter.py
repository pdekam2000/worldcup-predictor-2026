"""Read stored SQLite intelligence data for goal timing (priority 1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.goal_timing.data.fixture_ids import is_valid_fixture_id
from worldcup_predictor.goal_timing.leagues import GOAL_TIMING_ALLOWED_LEAGUE_KEYS, is_goal_timing_allowed_league
from worldcup_predictor.outcomes.models import GoalEvent


@dataclass
class HistoricalMatchContext:
    fixture_id: int
    competition_key: str
    home_team: str
    away_team: str
    kickoff_utc: str
    is_home_for_team: bool
    goal_events: list[GoalEvent]
    first_goal_minute: int | None
    first_goal_team: str | None
    has_goal_minute_data: bool


class StoredGoalTimingAdapter:
    """Loads finished historical matches and goal events from the intelligence DB."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._repo = FootballIntelligenceRepository(self._settings.sqlite_path or None)

    @property
    def repo(self) -> FootballIntelligenceRepository:
        return self._repo

    def get_target_fixture(self, fixture_id: int) -> dict[str, Any] | None:
        row = self._repo.get_fixture_row(fixture_id)
        if not row or int(row.get("is_placeholder") or 0):
            return None
        return row

    def load_goal_events(self, fixture_id: int) -> list[GoalEvent]:
        rows = self._repo.list_fixture_goal_events(int(fixture_id))
        return [GoalEvent.from_row(r) for r in rows]

    def team_history_before(
        self,
        team_name: str,
        *,
        before_kickoff: str,
        competition_keys: list[str] | None = None,
        limit: int = 40,
    ) -> list[HistoricalMatchContext]:
        keys = competition_keys or list(GOAL_TIMING_ALLOWED_LEAGUE_KEYS)
        rows = self._repo.list_team_finished_fixtures_before(
            team_name=team_name,
            before_kickoff=before_kickoff,
            competition_keys=keys,
            limit=limit,
        )
        return [self._to_context(row, team_name) for row in rows]

    def league_history_before(
        self,
        *,
        before_kickoff: str,
        competition_key: str,
        limit: int = 500,
    ) -> list[HistoricalMatchContext]:
        if not is_goal_timing_allowed_league(competition_key):
            return []
        rows = self._repo.list_finished_fixtures_before(
            before_kickoff=before_kickoff,
            competition_keys=[competition_key],
            limit=limit,
        )
        return [self._to_context(row, str(row.get("home_team") or "")) for row in rows]

    def league_coverage_rows(self) -> list[dict[str, Any]]:
        return self._repo.goal_timing_league_coverage(list(GOAL_TIMING_ALLOWED_LEAGUE_KEYS))

    def _to_context(self, row: dict[str, Any], team_name: str) -> HistoricalMatchContext:
        home = str(row.get("home_team") or "")
        away = str(row.get("away_team") or "")
        fid = int(row["fixture_id"])
        if not is_valid_fixture_id(fid):
            return HistoricalMatchContext(
                fixture_id=0,
                competition_key=str(row.get("competition_key") or ""),
                home_team=home,
                away_team=away,
                kickoff_utc=str(row.get("kickoff_utc") or ""),
                is_home_for_team=home == team_name,
                goal_events=[],
                first_goal_minute=None,
                first_goal_team=None,
                has_goal_minute_data=False,
            )
        events = self.load_goal_events(fid)
        fg_minute = row.get("first_goal_minute")
        if fg_minute is not None:
            try:
                fg_minute = int(fg_minute)
            except (TypeError, ValueError):
                fg_minute = None
        has_events = len(events) > 0
        has_fg = fg_minute is not None or has_events
        return HistoricalMatchContext(
            fixture_id=fid,
            competition_key=str(row.get("competition_key") or ""),
            home_team=home,
            away_team=away,
            kickoff_utc=str(row.get("kickoff_utc") or ""),
            is_home_for_team=home == team_name,
            goal_events=events,
            first_goal_minute=fg_minute,
            first_goal_team=row.get("first_goal_team"),
            has_goal_minute_data=has_fg,
        )

    @staticmethod
    def parse_kickoff(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
