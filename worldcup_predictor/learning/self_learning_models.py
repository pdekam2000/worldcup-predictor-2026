"""Dataclasses for Phase 42 — Self-Learning Accuracy Engine V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class AgentPerformanceMetrics:
    agent_key: str
    label: str
    samples: int = 0
    accuracy: float | None = None
    win_rate: float | None = None
    contribution_score: float = 0.0
    false_positive_rate: float | None = None
    false_negative_rate: float | None = None
    agent_reliability_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LeaguePerformanceMetrics:
    competition_key: str
    label: str
    samples: int = 0
    one_x_two_accuracy: float | None = None
    over_under_accuracy: float | None = None
    draw_accuracy: float | None = None
    league_reliability_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketTypeMetrics:
    market: str
    label: str
    samples: int = 0
    accuracy: float | None = None
    average_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CalibrationBucket:
    label: str
    predicted_confidence_avg: float
    actual_hit_rate: float | None
    count: int
    calibration_gap: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LearningRecommendation:
    category: str
    message: str
    priority: Literal["low", "medium", "high"] = "medium"
    requires_human_review: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SelfLearningReportV2:
    total_records: int
    verified_records: int
    pending_records: int
    agent_rankings: list[AgentPerformanceMetrics]
    league_rankings: list[LeaguePerformanceMetrics]
    market_type_metrics: list[MarketTypeMetrics]
    calibration_buckets: list[CalibrationBucket]
    insights: list[str]
    recommendations: list[LearningRecommendation]
    prediction_history_sample: list[dict[str, Any]] = field(default_factory=list)
    disclaimer: str = (
        "Self-learning reports are for human review only — no automatic weight changes are applied."
    )
    version: str = "v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "verified_records": self.verified_records,
            "pending_records": self.pending_records,
            "agent_rankings": [a.to_dict() for a in self.agent_rankings],
            "league_rankings": [l.to_dict() for l in self.league_rankings],
            "market_type_metrics": [m.to_dict() for m in self.market_type_metrics],
            "calibration_buckets": [c.to_dict() for c in self.calibration_buckets],
            "insights": self.insights,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "prediction_history_sample": self.prediction_history_sample,
            "disclaimer": self.disclaimer,
            "version": self.version,
        }
