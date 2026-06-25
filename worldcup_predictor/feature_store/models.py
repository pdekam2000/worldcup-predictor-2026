"""Dataclasses for Sportmonks xG feature store."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

RecordType = Literal["team_xg", "player_xg", "fixture_xg", "team_metric"]


@dataclass
class SportmonksXgRecord:
    sportmonks_fixture_id: int
    record_type: str
    metric_key: str
    xg_value: float
    captured_at: datetime
    source: str = "sportmonks_fixture"
    fixture_id: int | None = None
    league_id: int | None = None
    season_id: int | None = None
    home_team_id: int | None = None
    away_team_id: int | None = None
    participant_id: int | None = None
    player_id: int | None = None
    type_id: int | None = None
    type_name: str | None = None
    location: str | None = None
    raw_reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FixtureXgSummary:
    sportmonks_fixture_id: int
    captured_at: datetime
    source: str = "sportmonks_fixture"
    fixture_id: int | None = None
    league_id: int | None = None
    season_id: int | None = None
    home_team_id: int | None = None
    away_team_id: int | None = None
    match_started_at: datetime | None = None
    home_xg: float | None = None
    away_xg: float | None = None
    home_xga: float | None = None
    away_xga: float | None = None
    home_npxg: float | None = None
    away_npxg: float | None = None
    xg_total: float | None = None
    xg_difference: float | None = None
    home_team_recent_xg: float | None = None
    away_team_recent_xg: float | None = None
    home_team_recent_xga: float | None = None
    away_team_recent_xga: float | None = None
    attack_difference: float | None = None
    defense_difference: float | None = None
    momentum_difference: float | None = None
    aggregation_window: int | None = None
    features_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IngestManifestEntry:
    job_key: str
    sportmonks_fixture_id: int
    status: str
    processed_at: datetime
    league_id: int | None = None
    season_id: int | None = None
    api_calls: int = 0
    records_written: int = 0
    error: str | None = None


@dataclass
class IngestResult:
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
