"""Phase 58A — Elite Self Learning Engine models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

LearningRecommendation = Literal["SELF_LEARNING_READY", "NEEDS_SHADOW", "NOT_RECOMMENDED"]

VALID_RECOMMENDATIONS: frozenset[str] = frozenset(
    {"SELF_LEARNING_READY", "NEEDS_SHADOW", "NOT_RECOMMENDED"}
)

MARKET_IDS: tuple[str, ...] = (
    "1x2",
    "first_goal_team",
    "team_to_score_first",
    "anytime_goalscorer",
    "first_goalscorer",
    "goal_timing",
)

COMPONENT_IDS: tuple[str, ...] = (
    "lineup_intelligence",
    "goalscorer_intelligence",
    "market_behavior_intelligence",
    "odds_intelligence",
    "egie_historical_baseline",
    "hybrid_confidence_engine",
    "first_goal_team_v2",
    "player_form_store",
)

ATTRIBUTION_COMPONENTS: tuple[str, ...] = (
    "lineup_intelligence",
    "goalscorer_intelligence",
    "market_behavior_intelligence",
    "odds_intelligence",
    "egie_historical_baseline",
    "hybrid_confidence_engine",
)

ROLLING_WINDOWS: tuple[int, ...] = (100, 500, 1000)

ConfidenceTier = Literal["A", "B", "C", "D"]
OutcomeLabel = Literal["correct", "incorrect", "partial", "abstain"]


@dataclass
class MarketEvaluation:
    market_id: str
    prediction: Any
    reality: Any
    outcome: OutcomeLabel
    confidence: float
    tier: ConfidenceTier
    brier: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "prediction": self.prediction,
            "reality": self.reality,
            "outcome": self.outcome,
            "confidence": self.confidence,
            "tier": self.tier,
            "brier": self.brier,
        }


@dataclass
class ComponentAttribution:
    component_id: str
    prediction: Any
    weight_used: float
    confidence: float
    helped: bool
    hurt: bool
    neutral: bool
    delta_vs_reality: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "prediction": self.prediction,
            "weight_used": self.weight_used,
            "confidence": self.confidence,
            "helped": self.helped,
            "hurt": self.hurt,
            "neutral": self.neutral,
            "delta_vs_reality": self.delta_vs_reality,
        }


@dataclass
class PostMatchEvaluation:
    fixture_id: int
    sportmonks_fixture_id: int | None
    league_id: int | None
    competition_key: str | None
    kickoff_utc: str | None
    evaluated_at: str
    markets: list[MarketEvaluation]
    attributions: list[ComponentAttribution]
    fusion_correct: bool
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "sportmonks_fixture_id": self.sportmonks_fixture_id,
            "league_id": self.league_id,
            "competition_key": self.competition_key,
            "kickoff_utc": self.kickoff_utc,
            "evaluated_at": self.evaluated_at,
            "markets": [m.to_dict() for m in self.markets],
            "attributions": [a.to_dict() for a in self.attributions],
            "fusion_correct": self.fusion_correct,
            "meta": self.meta,
        }


@dataclass
class ComponentScore:
    component_id: str
    market_id: str
    league_id: int | None
    window: int
    n: int
    hit_rate: float
    help_rate: float
    hurt_rate: float
    mean_confidence: float
    brier: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "market_id": self.market_id,
            "league_id": self.league_id,
            "window": self.window,
            "n": self.n,
            "hit_rate": self.hit_rate,
            "help_rate": self.help_rate,
            "hurt_rate": self.hurt_rate,
            "mean_confidence": self.mean_confidence,
            "brier": self.brier,
        }


@dataclass
class AdaptiveWeightRecommendation:
    component_id: str
    market_id: str
    current_weight: float
    recommended_weight: float
    delta: float
    direction: Literal["increase", "decrease", "hold"]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "market_id": self.market_id,
            "current_weight": self.current_weight,
            "recommended_weight": self.recommended_weight,
            "delta": self.delta,
            "direction": self.direction,
            "reason": self.reason,
        }
