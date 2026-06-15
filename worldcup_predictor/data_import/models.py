from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

ImportSource = Literal["api-football", "demo", "csv", "merged"]


@dataclass
class ImportedMatchRow:
    """Normalized row for backtest CSV export."""

    fixture_id: int
    date: datetime
    competition: str
    round: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    halftime_home_goals: int | None = None
    halftime_away_goals: int | None = None
    venue: str = "Unknown"
    referee: str | None = None
    odds_home: float | None = None
    odds_draw: float | None = None
    odds_away: float | None = None
    over_2_5_odds: float | None = None
    under_2_5_odds: float | None = None
    source: ImportSource = "api-football"
    missing_fields: list[str] = field(default_factory=list)

    def to_csv_dict(self) -> dict[str, str]:
        return {
            "fixture_id": str(self.fixture_id),
            "date": self.date.strftime("%Y-%m-%d"),
            "competition": self.competition,
            "round": self.round,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "home_goals": str(self.home_goals),
            "away_goals": str(self.away_goals),
            "halftime_home_goals": "" if self.halftime_home_goals is None else str(self.halftime_home_goals),
            "halftime_away_goals": "" if self.halftime_away_goals is None else str(self.halftime_away_goals),
            "venue": self.venue,
            "referee": self.referee or "",
            "odds_home": "" if self.odds_home is None else str(self.odds_home),
            "odds_draw": "" if self.odds_draw is None else str(self.odds_draw),
            "odds_away": "" if self.odds_away is None else str(self.odds_away),
            "over_2_5_odds": "" if self.over_2_5_odds is None else str(self.over_2_5_odds),
            "under_2_5_odds": "" if self.under_2_5_odds is None else str(self.under_2_5_odds),
        }


@dataclass
class ImportStats:
    cache_hits: int = 0
    live_requests: int = 0
    odds_fetched: int = 0
    odds_missing: int = 0


@dataclass
class ImportResult:
    rows: list[ImportedMatchRow] = field(default_factory=list)
    imported_count: int = 0
    skipped_count: int = 0
    requested_competitions: list[str] = field(default_factory=list)
    requested_seasons: list[int] = field(default_factory=list)
    missing_fields_summary: dict[str, int] = field(default_factory=dict)
    api_errors: list[str] = field(default_factory=list)
    stats: ImportStats = field(default_factory=ImportStats)
    source_label: ImportSource = "api-football"
    data_quality_notes: list[str] = field(default_factory=list)
    success: bool = False
    message: str = ""

    def record_missing(self, fields: list[str]) -> None:
        for field_name in fields:
            self.missing_fields_summary[field_name] = (
                self.missing_fields_summary.get(field_name, 0) + 1
            )


@dataclass
class ExportResult:
    output_path: str
    rows_written: int
    rows_merged: int
    overwritten: bool
    source_label: ImportSource
    validation_errors: list[str] = field(default_factory=list)
