"""Models for First Goal Intelligence V2 — informational only."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

FirstGoalTeamSide = Literal["home", "away", "no_goal", "unknown"]
MinuteBand = Literal["0-15", "16-30", "31-45", "46-60", "61-75", "76-90", "no_goal", "unknown"]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class FirstGoalScorerCandidateV2:
    player: str
    team: str
    score: float
    reason: str
    data_source: str
    position: str = ""

    @property
    def confidence(self) -> float:
        return round(_clamp(self.score, 0, 100), 1)

    def to_phase51_dict(self) -> dict[str, Any]:
        return {
            "player_name": self.player,
            "team": self.team,
            "position": self.position or "",
            "confidence": self.confidence,
            "reason": self.reason,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "player_name": self.player,
            "confidence": self.confidence,
        }


@dataclass
class FirstGoalIntelligenceV2Result:
    fixture_id: int
    first_goal_team: FirstGoalTeamSide
    first_goal_team_display: str
    likely_first_goal_scorers: list[FirstGoalScorerCandidateV2] = field(default_factory=list)
    first_goal_minute_band: MinuteBand = "31-45"
    confidence: float = 0.0
    risk_flags: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    data_availability: dict[str, bool] = field(default_factory=dict)
    data_available: bool = False
    player_data_unavailable: bool = False
    player_data_message: str | None = None
    summary: str = ""
    disclaimer: str = (
        "First-goal analysis is informational only — minute bands are approximate, "
        "not exact predictions. Never betting advice."
    )

    def to_dict(self) -> dict[str, Any]:
        likely_scorers = [c.to_phase51_dict() for c in self.likely_first_goal_scorers]
        return {
            "fixture_id": self.fixture_id,
            "first_goal_team": self.first_goal_team,
            "first_goal_team_display": self.first_goal_team_display,
            "first_goal_minute_band": self.first_goal_minute_band,
            "likely_scorers": likely_scorers,
            "likely_first_goal_scorers": [c.to_dict() for c in self.likely_first_goal_scorers],
            "confidence": round(self.confidence, 1),
            "data_available": self.data_available,
            "risk_flags": list(self.risk_flags),
            "reasoning": list(self.reasoning),
            "data_availability": dict(self.data_availability),
            "player_data_unavailable": self.player_data_unavailable,
            "player_data_message": self.player_data_message,
            "summary": self.summary,
            "disclaimer": self.disclaimer,
        }
