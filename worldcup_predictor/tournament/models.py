"""Structured models for Phase 43 — Tournament Intelligence V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

RotationRisk = Literal["Low", "Medium", "High"]
QualificationLabel = Literal[
    "unknown",
    "already_qualified",
    "already_eliminated",
    "must_win",
    "draw_acceptable",
    "goal_difference_critical",
]


@dataclass
class TeamTournamentSide:
    team_name: str
    qualification_status: QualificationLabel = "unknown"
    qualification_probability: float = 50.0
    elimination_risk: float = 50.0
    motivation_boost: float = 0.0
    rank: int | None = None
    points: int | None = None
    goal_difference: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TournamentPredictionImpact:
    home_adjustment: float = 0.0
    away_adjustment: float = 0.0
    draw_adjustment: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass
class TournamentIntelligenceResult:
    match_context: str
    competition_type: str
    tournament_name: str
    home: TeamTournamentSide
    away: TeamTournamentSide
    rotation_risk: RotationRisk
    pressure_score: float
    risk_flags: list[str] = field(default_factory=list)
    prediction_impact: TournamentPredictionImpact = field(default_factory=TournamentPredictionImpact)
    summary: str = ""
    data_available: bool = False
    version: str = "v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_context": self.match_context,
            "competition_type": self.competition_type,
            "tournament_name": self.tournament_name,
            "home": self.home.to_dict(),
            "away": self.away.to_dict(),
            "rotation_risk": self.rotation_risk,
            "pressure_score": self.pressure_score,
            "risk_flags": self.risk_flags,
            "prediction_impact": self.prediction_impact.to_dict(),
            "summary": self.summary,
            "data_available": self.data_available,
            "version": self.version,
        }
