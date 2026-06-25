"""Goalscorer shadow engine models (Phase 54K — research only)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

FEATURE_COLUMNS = (
    "starter_probability",
    "expected_minutes",
    "goals_last_3",
    "goals_last_5",
    "goals_last_10",
    "goals_per_90",
    "assists_last_5",
    "shots_last_5",
    "shots_on_target_last_5",
    "xg_last_5",
    "xg_last_10",
    "xg_per_90",
    "recent_form_score",
    "team_strength_proxy",
    "opponent_defense_proxy",
)

SCORE_COLUMNS = (
    "goals_per_90_score",
    "xg_per_90_score",
    "starter_weighted_score",
    "combined_score",
)

VALID_RECOMMENDATIONS = frozenset(
    {
        "GOALSCORER_HIGH_VALUE",
        "GOALSCORER_MEDIUM_VALUE",
        "GOALSCORER_LOW_VALUE",
        "GOALSCORER_INSUFFICIENT_DATA",
        "GOALSCORER_NO_VALUE",
    }
)


@dataclass
class GoalscorerDatasetSummary:
    total_rows: int = 0
    eligible_rows: int = 0
    unusable_rows: int = 0
    fixtures: int = 0
    anytime_positive: int = 0
    first_goal_positive: int = 0
    train_rows: int = 0
    val_rows: int = 0
    test_rows: int = 0
    date_min: str | None = None
    date_max: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TopKMetrics:
    market: str
    model: str
    fixtures_evaluated: int = 0
    top1_hit: float | None = None
    top3_hit: float | None = None
    top5_hit: float | None = None
    precision_at_1: float | None = None
    precision_at_3: float | None = None
    precision_at_5: float | None = None
    mean_reciprocal_rank: float | None = None
    top3_recall: float | None = None
    top5_recall: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BacktestReport:
    generated_at: str
    split: dict[str, Any] = field(default_factory=dict)
    anytime: list[TopKMetrics] = field(default_factory=list)
    first_goal: list[TopKMetrics] = field(default_factory=list)
    most_likely: list[TopKMetrics] = field(default_factory=list)
    feature_importance_proxy: dict[str, float] = field(default_factory=dict)
    odds_alignment: dict[str, Any] = field(default_factory=dict)
    recommendation: str = "GOALSCORER_INSUFFICIENT_DATA"
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "split": self.split,
            "anytime": [m.to_dict() for m in self.anytime],
            "first_goal": [m.to_dict() for m in self.first_goal],
            "most_likely": [m.to_dict() for m in self.most_likely],
            "feature_importance_proxy": self.feature_importance_proxy,
            "odds_alignment": self.odds_alignment,
            "recommendation": self.recommendation,
            "limitations": self.limitations,
        }
