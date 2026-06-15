"""Structured models for Phase 38 — Lineup Intelligence V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

GoalkeeperStatus = Literal["main", "backup", "unknown"]


@dataclass
class PredictionImpact:
    home_adjustment: float = 0.0
    away_adjustment: float = 0.0
    over25_adjustment: float = 0.0
    under25_adjustment: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass
class TeamLineupSide:
    lineup_available: bool = False
    official_lineup: bool = False
    starting_xi_count: int = 0
    substitutes_count: int = 0
    missing_key_players: list[str] = field(default_factory=list)
    goalkeeper_status: GoalkeeperStatus = "unknown"
    goalkeeper_name: str | None = None
    rotation_count: int | None = None
    lineup_strength: float = 0.0
    confidence: float = 0.0
    risk_flags: list[str] = field(default_factory=list)
    formation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LineupIntelligenceResult:
    home: TeamLineupSide
    away: TeamLineupSide
    summary: str
    prediction_impact: PredictionImpact
    version: str = "v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "home": self.home.to_dict(),
            "away": self.away.to_dict(),
            "summary": self.summary,
            "prediction_impact": self.prediction_impact.to_dict(),
            "version": self.version,
        }
