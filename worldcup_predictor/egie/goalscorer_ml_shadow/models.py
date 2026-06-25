"""Goalscorer ML shadow models and constants (Phase 54L)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

FEATURE_GROUP_A = (
    "goals_last_3",
    "goals_last_5",
    "goals_last_10",
    "assists_last_5",
    "recent_form_score",
)

FEATURE_GROUP_B = (
    "shots_last_5",
    "shots_on_target_last_5",
)

FEATURE_GROUP_C = (
    "xg_last_5",
    "xg_last_10",
    "xg_per_90",
)

FEATURE_GROUP_D = (
    "starter_probability",
    "lineup_status_starter",
    "lineup_status_bench",
    "expected_minutes",
    "captain",
)

ML_FEATURE_COLUMNS = FEATURE_GROUP_A + FEATURE_GROUP_B + FEATURE_GROUP_C + FEATURE_GROUP_D

TARGETS = {
    "anytime": "target_anytime",
    "first_goal": "target_first_goal",
    "most_likely": "target_most_likely",
}

MODEL_NAMES = ("logistic_regression", "lightgbm", "catboost", "ensemble", "combined_baseline")

VALID_RECOMMENDATIONS = frozenset(
    {
        "GOALSCORER_HIGH_VALUE",
        "GOALSCORER_MEDIUM_VALUE",
        "GOALSCORER_LOW_VALUE",
        "GOALSCORER_NO_VALUE",
    }
)


@dataclass
class RankingMetrics:
    market: str
    model: str
    fixtures_evaluated: int = 0
    top1_hit: float | None = None
    top3_hit: float | None = None
    top5_hit: float | None = None
    mrr: float | None = None
    recall_at_3: float | None = None
    recall_at_5: float | None = None
    precision_at_1: float | None = None
    precision_at_3: float | None = None
    precision_at_5: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CalibrationMetrics:
    market: str
    model: str
    method: str
    ece: float | None = None
    brier: float | None = None
    n_samples: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MLShadowReport:
    generated_at: str
    dataset: dict[str, Any] = field(default_factory=dict)
    ranking: list[RankingMetrics] = field(default_factory=list)
    calibration: list[CalibrationMetrics] = field(default_factory=list)
    feature_importance: dict[str, Any] = field(default_factory=dict)
    odds_overlay: dict[str, Any] = field(default_factory=dict)
    baseline_comparison: dict[str, Any] = field(default_factory=dict)
    recommendation: str = "GOALSCORER_LOW_VALUE"
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "dataset": self.dataset,
            "ranking": [r.to_dict() for r in self.ranking],
            "calibration": [c.to_dict() for c in self.calibration],
            "feature_importance": self.feature_importance,
            "odds_overlay": self.odds_overlay,
            "baseline_comparison": self.baseline_comparison,
            "recommendation": self.recommendation,
            "limitations": self.limitations,
        }
