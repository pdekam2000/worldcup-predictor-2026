"""Dataclasses for lineup / player feature store."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class PlayerMatchStatRecord:
    sportmonks_fixture_id: int
    player_id: int
    captured_at: datetime
    source: str = "sportmonks_cache"
    fixture_id: int | None = None
    player_name: str | None = None
    team_id: int | None = None
    position: str | None = None
    starter: bool = False
    captain: bool = False
    minutes: int = 0
    goals: int = 0
    assists: int = 0
    shots: int = 0
    shots_on_target: int = 0
    rating: float | None = None
    xg: float | None = None
    xa: float | None = None
    yellow_cards: int = 0
    red_cards: int = 0
    season_id: int | None = None
    league_id: int | None = None
    match_date: datetime | None = None
    raw_reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlayerRollingFeatureRecord:
    sportmonks_fixture_id: int
    player_id: int
    captured_at: datetime
    source: str = "sportmonks_cache"
    fixture_id: int | None = None
    team_id: int | None = None
    league_id: int | None = None
    season_id: int | None = None
    match_date: datetime | None = None
    goals_last_3: int = 0
    goals_last_5: int = 0
    goals_last_10: int = 0
    assists_last_5: int = 0
    minutes_last_5: int = 0
    starts_last_5: int = 0
    shots_last_5: int = 0
    shots_on_target_last_5: int = 0
    xg_last_5: float | None = None
    xg_last_10: float | None = None
    goals_per_90: float | None = None
    xg_per_90: float | None = None
    starter_probability: float | None = None
    recent_form_score: float | None = None
    starter: bool = False
    captain: bool = False
    position: str | None = None
    position_group: str | None = None
    formation: str | None = None
    goalkeeper_player_id: int | None = None
    captain_player_id: int | None = None
    lineup_available: bool = False
    lineup_quality_score: float | None = None
    starting_xi: list[int] = field(default_factory=list)
    bench: list[int] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlayerIngestResult:
    job_key: str
    fixtures_processed: int = 0
    fixtures_imported: int = 0
    fixtures_skipped: int = 0
    fixtures_empty: int = 0
    fixtures_error: int = 0
    player_rows_written: int = 0
    rolling_rows_written: int = 0
    api_calls_live: int = 0
    api_calls_cached: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
