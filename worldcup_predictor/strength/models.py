"""Structured models for Phase 44 — ELO & Team Strength Intelligence V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

MatchupSide = Literal["home", "away", "balanced"]


@dataclass
class FormWindowStats:
    matches: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points_per_match: float = 0.0
    form_string: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TeamStrengthSide:
    team_name: str
    team_id: int | None = None
    elo: float = 1500.0
    form_last_5: FormWindowStats = field(default_factory=FormWindowStats)
    form_last_10: FormWindowStats = field(default_factory=FormWindowStats)
    form_last_20: FormWindowStats = field(default_factory=FormWindowStats)
    attack_strength: float = 50.0
    defense_strength: float = 50.0
    overall_team_strength: float = 50.0
    momentum_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_name": self.team_name,
            "team_id": self.team_id,
            "elo": round(self.elo, 1),
            "form_last_5": self.form_last_5.to_dict(),
            "form_last_10": self.form_last_10.to_dict(),
            "form_last_20": self.form_last_20.to_dict(),
            "attack_strength": round(self.attack_strength, 1),
            "defense_strength": round(self.defense_strength, 1),
            "overall_team_strength": round(self.overall_team_strength, 1),
            "momentum_score": round(self.momentum_score, 1),
        }


@dataclass
class MatchupAdvantage:
    side: MatchupSide = "balanced"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StrengthPredictionImpact:
    home_adjustment: float = 0.0
    away_adjustment: float = 0.0
    draw_adjustment: float = 0.0
    over25_adjustment: float = 0.0
    under25_adjustment: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {k: round(v, 2) for k, v in asdict(self).items()}


@dataclass
class EloTeamStrengthResult:
    home: TeamStrengthSide
    away: TeamStrengthSide
    home_elo: float
    away_elo: float
    elo_difference: float
    matchup_advantage: MatchupAdvantage
    risk_flags: list[str] = field(default_factory=list)
    prediction_impact: StrengthPredictionImpact = field(default_factory=StrengthPredictionImpact)
    summary: str = ""
    data_available: bool = False
    sample_size_home: int = 0
    sample_size_away: int = 0
    version: str = "v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "home": self.home.to_dict(),
            "away": self.away.to_dict(),
            "home_elo": round(self.home_elo, 1),
            "away_elo": round(self.away_elo, 1),
            "elo_difference": round(self.elo_difference, 1),
            "matchup_advantage": self.matchup_advantage.to_dict(),
            "risk_flags": self.risk_flags,
            "prediction_impact": self.prediction_impact.to_dict(),
            "summary": self.summary,
            "data_available": self.data_available,
            "sample_size_home": self.sample_size_home,
            "sample_size_away": self.sample_size_away,
            "version": self.version,
        }
