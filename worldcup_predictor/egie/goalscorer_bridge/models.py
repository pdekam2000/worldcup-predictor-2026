"""Phase 54O goalscorer bridge models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

BridgeConfidence = Literal["HIGH", "MEDIUM", "LOW", "UNMAPPED"]

VALID_RECOMMENDATIONS = frozenset(
    {
        "GOALSCORER_HIGH_VALUE",
        "GOALSCORER_MEDIUM_VALUE",
        "GOALSCORER_ODDS_BLOCKED",
        "GOALSCORER_NOT_READY",
    }
)

EDGE_VALUE = Literal["HIGH", "MEDIUM", "LOW"]


@dataclass
class FixtureBridge:
    api_football_fixture_id: int
    internal_fixture_id: int
    sportmonks_fixture_id: int | None
    home_team: str
    away_team: str
    home_team_id: int | None
    away_team_id: int | None
    league: str
    season: int | None
    match_date: str | None
    status: str | None
    bridge_confidence: BridgeConfidence
    bridge_method: str
    sportmonks_lineups_available: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BridgeAuditSummary:
    total_api_gs_fixtures: int = 0
    mapped: int = 0
    partial: int = 0
    unmapped: int = 0
    with_sportmonks_lineups: int = 0
    player_mapping_rate: float = 0.0
    player_mapped: int = 0
    player_unmapped: int = 0
    confidence_high: int = 0
    confidence_medium: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
