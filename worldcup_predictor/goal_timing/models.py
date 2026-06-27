"""Domain models for Elite Goal Timing engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

GoalTimingTeamPick = Literal["home", "away", "none"]
GoalTimingEvalStatus = Literal["correct", "wrong", "partial", "pending"]


@dataclass
class GoalTimingAgentOutput:
    agent_name: str
    status: str
    signals: dict[str, Any] = field(default_factory=dict)
    impact_score: float | None = None
    missing_data: list[str] = field(default_factory=list)
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GoalTimingPredictionResult:
    fixture_id: int
    competition_key: str
    home_team: str
    away_team: str
    match_date: datetime | None
    first_goal_team: GoalTimingTeamPick
    first_goal_time_range: str | None
    display_estimated_first_goal_minute: float | None
    bucket_representative_minute: float | None
    weighted_average_minute: float | None
    model_confidence_score: float
    home_team_goal_probability_by_range: dict[str, float]
    away_team_goal_probability_by_range: dict[str, float]
    no_goal_before_minute_probability: dict[str, float]
    confidence_score: float
    data_quality_score: float
    explanation: str
    specialist_agent_breakdown: dict[str, Any]
    model_version: str
    no_prediction_flag: bool = False
    no_bet_flag: bool = True
    predicted_at: datetime | None = None

    def to_dict(self, *, include_audit: bool = False) -> dict[str, Any]:
        payload = asdict(self)
        if self.match_date:
            payload["match_date"] = self.match_date.isoformat()
        if self.predicted_at:
            payload["predicted_at"] = self.predicted_at.isoformat()
        # Public API/UI — display minute only (backward-compat alias)
        payload["estimated_first_goal_minute"] = self.display_estimated_first_goal_minute
        if include_audit:
            payload["audit_details"] = {
                "weighted_average_minute": self.weighted_average_minute,
                "model_confidence_score": self.model_confidence_score,
                "bucket_representative_minute": self.bucket_representative_minute,
            }
        return payload


@dataclass
class GoalTimingEvaluationResult:
    fixture_id: int
    prediction_id: str
    actual_first_goal_team: str | None
    actual_first_goal_minute: int | None
    actual_first_goal_time_range: str | None
    first_goal_team_status: GoalTimingEvalStatus
    time_range_status: GoalTimingEvalStatus
    minute_tolerance_status: GoalTimingEvalStatus
    evaluated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.evaluated_at:
            payload["evaluated_at"] = self.evaluated_at.isoformat()
        return payload
