"""Structured models for Phase 45 — xG & Chance Quality Intelligence V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ConversionLabel = Literal["poor", "average", "clinical", "unsustainably_clinical", "unknown"]
MatchupSide = Literal["home", "away", "balanced"]
DataMode = Literal["xg", "fallback", "unavailable"]


@dataclass
class TeamChanceQualitySide:
    team_name: str
    team_id: int | None = None
    xg: float | None = None
    xg_per_match: float | None = None
    attack_chance_quality: float = 50.0
    defensive_chance_prevention: float = 50.0
    conversion_efficiency: float = 0.0
    conversion_label: ConversionLabel = "unknown"
    shots_total: float | None = None
    shots_on_target: float | None = None
    big_chances: float | None = None
    goals: float | None = None
    blocked_shots: float | None = None
    goalkeeper_saves: float | None = None
    inside_box_shots: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_name": self.team_name,
            "team_id": self.team_id,
            "xg": round(self.xg, 2) if self.xg is not None else None,
            "xg_per_match": round(self.xg_per_match, 2) if self.xg_per_match is not None else None,
            "attack_chance_quality": round(self.attack_chance_quality, 1),
            "defensive_chance_prevention": round(self.defensive_chance_prevention, 1),
            "conversion_efficiency": round(self.conversion_efficiency, 3),
            "conversion_label": self.conversion_label,
            "shots_total": self.shots_total,
            "shots_on_target": self.shots_on_target,
            "big_chances": self.big_chances,
            "goals": self.goals,
            "blocked_shots": self.blocked_shots,
            "goalkeeper_saves": self.goalkeeper_saves,
            "inside_box_shots": self.inside_box_shots,
        }


@dataclass
class ChanceQualityAdvantage:
    side: MatchupSide = "balanced"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChanceQualityPredictionImpact:
    home_adjustment: float = 0.0
    away_adjustment: float = 0.0
    draw_adjustment: float = 0.0
    over25_adjustment: float = 0.0
    under25_adjustment: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {k: round(v, 2) for k, v in asdict(self).items()}


@dataclass
class XGChanceQualityResult:
    home: TeamChanceQualitySide
    away: TeamChanceQualitySide
    xg_available: bool = False
    chance_quality_available: bool = False
    data_mode: DataMode = "unavailable"
    home_chance_edge: float = 0.0
    away_chance_edge: float = 0.0
    goals_pressure_score: float = 50.0
    chance_quality_advantage: ChanceQualityAdvantage = field(default_factory=ChanceQualityAdvantage)
    risk_flags: list[str] = field(default_factory=list)
    prediction_impact: ChanceQualityPredictionImpact = field(default_factory=ChanceQualityPredictionImpact)
    summary: str = ""
    version: str = "v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "xg_available": self.xg_available,
            "chance_quality_available": self.chance_quality_available,
            "data_mode": self.data_mode,
            "home": self.home.to_dict(),
            "away": self.away.to_dict(),
            "home_chance_edge": round(self.home_chance_edge, 1),
            "away_chance_edge": round(self.away_chance_edge, 1),
            "goals_pressure_score": round(self.goals_pressure_score, 1),
            "chance_quality_advantage": self.chance_quality_advantage.to_dict(),
            "risk_flags": self.risk_flags,
            "prediction_impact": self.prediction_impact.to_dict(),
            "summary": self.summary,
            "version": self.version,
        }
