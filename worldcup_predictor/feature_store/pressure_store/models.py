"""Dataclasses for Sportmonks Pressure feature store."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SportmonksPressureRecord:
    sportmonks_fixture_id: int
    pressure_row_id: int
    participant_id: int
    minute: int
    pressure_value: float
    captured_at: datetime
    source: str = "sportmonks_fixture"
    fixture_id: int | None = None
    league_id: int | None = None
    season_id: int | None = None
    team_id: int | None = None
    raw_reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FixturePressureSummary:
    sportmonks_fixture_id: int
    captured_at: datetime
    source: str = "sportmonks_fixture"
    fixture_id: int | None = None
    league_id: int | None = None
    season_id: int | None = None
    home_team_id: int | None = None
    away_team_id: int | None = None
    match_started_at: datetime | None = None
    pressure_row_count: int = 0
    unique_minutes: int = 0
    first_goal_minute: int | None = None
    features_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PressureIngestResult:
    job_key: str
    fixtures_processed: int = 0
    fixtures_imported: int = 0
    fixtures_skipped: int = 0
    fixtures_empty: int = 0
    fixtures_error: int = 0
    records_written: int = 0
    api_calls_live: int = 0
    api_calls_cached: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
