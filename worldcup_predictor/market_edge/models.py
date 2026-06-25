"""Phase 55A market edge discovery models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

MARKET_IDS: tuple[str, ...] = (
    "1x2",
    "double_chance",
    "btts",
    "over_0_5_ht",
    "over_1_5",
    "over_2_5",
    "team_to_score_first",
    "first_goal_team",
    "anytime_goalscorer",
    "first_goalscorer",
    "goal_range",
    "goal_timing",
    "correct_score",
)

VALID_RECOMMENDATIONS = frozenset(
    {
        "ANYTIME_GOALSCORER_ODDS_EXPANSION",
        "FIRST_GOAL_TEAM_REFINEMENT",
        "BTTS_CALIBRATION",
        "OVER_2_5_EDGE",
        "ONE_X_TWO_HARMONIZATION",
        "GOAL_RANGE_RESEARCH",
        "MULTI_MARKET_PORTFOLIO",
    }
)


@dataclass
class MarketProfile:
    market_id: str
    display_name: str
    dataset_size: int = 0
    coverage_pct: float = 0.0
    accuracy: float | None = None
    accuracy_metric: str = "accuracy"
    baseline_accuracy: float | None = None
    calibration_ece: float | None = None
    brier: float | None = None
    stability_score: float = 0.0
    odds_availability_pct: float = 0.0
    roi_potential: float = 0.0
    production_status: str = "none"
    infrastructure_tier: str = "gap"
    data_sources: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoredMarket:
    market_id: str
    display_name: str
    market_edge_score: float
    profile: MarketProfile
    score_breakdown: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "display_name": self.display_name,
            "market_edge_score": self.market_edge_score,
            "score_breakdown": self.score_breakdown,
            "profile": self.profile.to_dict(),
        }
