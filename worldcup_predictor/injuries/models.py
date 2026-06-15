"""Structured models for Phase 39 — Injury & Suspension Intelligence V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

PlayerStatus = Literal["confirmed", "doubtful", "suspended", "expected_return", "unknown"]
PositionGroup = Literal["Goalkeeper", "Defender", "Midfielder", "Forward", "Unknown"]


@dataclass
class UnavailablePlayer:
    name: str
    player_id: int | None
    status: PlayerStatus
    position_group: PositionGroup
    importance_score: float
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PositionLosses:
    defensive_loss: float = 0.0
    midfield_loss: float = 0.0
    attacking_loss: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass
class TeamInjurySide:
    unavailable_players: list[UnavailablePlayer] = field(default_factory=list)
    confirmed_count: int = 0
    doubtful_count: int = 0
    suspended_count: int = 0
    injury_impact_score: float = 0.0
    impact_band: str = "negligible"
    position_losses: PositionLosses = field(default_factory=PositionLosses)
    confidence: float = 0.0
    risk_flags: list[str] = field(default_factory=list)
    data_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "unavailable_players": [p.to_dict() for p in self.unavailable_players],
            "confirmed_count": self.confirmed_count,
            "doubtful_count": self.doubtful_count,
            "suspended_count": self.suspended_count,
            "injury_impact_score": self.injury_impact_score,
            "impact_band": self.impact_band,
            "position_losses": self.position_losses.to_dict(),
            "confidence": self.confidence,
            "risk_flags": self.risk_flags,
            "data_available": self.data_available,
        }


@dataclass
class InjuryPredictionImpact:
    home_adjustment: float = 0.0
    away_adjustment: float = 0.0
    over25_adjustment: float = 0.0
    under25_adjustment: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass
class InjuryIntelligenceResult:
    home: TeamInjurySide
    away: TeamInjurySide
    summary: str
    prediction_impact: InjuryPredictionImpact
    version: str = "v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "home": self.home.to_dict(),
            "away": self.away.to_dict(),
            "summary": self.summary,
            "prediction_impact": self.prediction_impact.to_dict(),
            "version": self.version,
        }
