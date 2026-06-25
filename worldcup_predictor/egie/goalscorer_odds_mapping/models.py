"""Goalscorer odds mapping models (Phase 54M)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"
CONFIDENCE_UNMAPPED = "UNMAPPED"

USABLE_CONFIDENCES = frozenset({CONFIDENCE_HIGH, CONFIDENCE_MEDIUM})

VALID_RECOMMENDATIONS = frozenset(
    {
        "GOALSCORER_ODDS_READY",
        "NEED_MORE_GOALSCORER_ODDS",
        "NEED_BETTER_PLAYER_MAPPING",
        "GOALSCORER_ODDS_NOT_USEFUL",
    }
)


@dataclass
class RawOddsSelection:
    sportmonks_fixture_id: int
    bookmaker: str
    market: str
    label: str
    selection_name: str
    odds: float
    implied_probability: float
    timestamp: str | None = None
    finished: bool = False
    league_id: int | None = None
    season_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MappedOddsSelection:
    sportmonks_fixture_id: int
    player_id: int
    player_name: str
    selection_name: str
    market: str
    bookmaker: str
    odds: float
    implied_probability: float
    mapping_confidence: str
    mapping_method: str
    mapping_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MappingSummary:
    fixtures_audited: int = 0
    fixtures_with_goalscorer_odds: int = 0
    bookmaker_count: int = 0
    market_count: int = 0
    selection_count: int = 0
    mapped_count: int = 0
    unmapped_count: int = 0
    mapping_rate: float = 0.0
    confidence_high: int = 0
    confidence_medium: int = 0
    confidence_low: int = 0
    historical_fixtures: int = 0
    upcoming_fixtures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
