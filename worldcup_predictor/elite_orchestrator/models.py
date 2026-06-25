"""Phase 57A — Elite Prediction Orchestrator models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

ComponentStatus = Literal["validated", "rejected", "baseline"]
ReadinessLevel = Literal["READY", "PARTIAL", "RESEARCH", "BLOCKED"]
ConfidenceTier = Literal["A", "B", "C", "D"]

MARKET_IDS: tuple[str, ...] = (
    "1x2",
    "first_goal_team",
    "team_to_score_first",
    "anytime_goalscorer",
    "first_goalscorer",
    "goal_timing",
)

INPUT_SOURCES: tuple[str, ...] = (
    "lineups",
    "player_store",
    "goalscorer_intelligence",
    "market_behavior_intelligence",
    "odds",
    "historical_models",
)

REJECTED_COMPONENTS: frozenset[str] = frozenset(
    {
        "pressure_index",
        "team_context",
        "availability_overlay",
        "team_xg_general",
        "full_feature_blend",
    }
)


class FusionSignal(str, Enum):
    MODEL_AGREEMENT = "model_agreement"
    MARKET_AGREEMENT = "market_agreement"
    MBI_PRIOR = "mbi_prior"
    ODDS_CONFIDENCE = "odds_confidence"
    DATA_QUALITY = "data_quality"


@dataclass(frozen=True)
class ComponentRecord:
    component_id: str
    name: str
    purpose: str
    confidence: str
    supported_markets: tuple[str, ...]
    data_dependencies: tuple[str, ...]
    latency_ms: int
    readiness: ReadinessLevel
    status: ComponentStatus
    phase_source: str
    package_path: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "name": self.name,
            "purpose": self.purpose,
            "confidence": self.confidence,
            "supported_markets": list(self.supported_markets),
            "data_dependencies": list(self.data_dependencies),
            "latency_ms": self.latency_ms,
            "readiness": self.readiness,
            "status": self.status,
            "phase_source": self.phase_source,
            "package_path": self.package_path,
            "notes": self.notes,
        }


@dataclass
class GraphNode:
    node_id: str
    node_type: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    component_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "component_id": self.component_id,
        }


@dataclass
class MarketReadiness:
    market_id: str
    readiness: ReadinessLevel
    primary_components: list[str]
    blockers: list[str]
    shadow_ready: bool
    production_ready: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "readiness": self.readiness,
            "primary_components": self.primary_components,
            "blockers": self.blockers,
            "shadow_ready": self.shadow_ready,
            "production_ready": self.production_ready,
            "notes": self.notes,
        }


@dataclass
class ComponentContribution:
    component_id: str
    weight: float
    prediction: Any
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "weight": self.weight,
            "prediction": self.prediction,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass
class MarketShadowOutput:
    market_id: str
    prediction: Any
    confidence: float
    tier: ConfidenceTier
    evidence: dict[str, Any]
    reasoning: list[str]
    component_contributions: list[ComponentContribution]

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "prediction": self.prediction,
            "confidence": self.confidence,
            "tier": self.tier,
            "evidence": self.evidence,
            "reasoning": self.reasoning,
            "component_contributions": [c.to_dict() for c in self.component_contributions],
        }


@dataclass
class EliteShadowPrediction:
    """Single internal prediction object — shadow only, not production."""

    fixture_id: int
    sportmonks_fixture_id: int | None
    competition_key: str
    generated_at: str
    markets: dict[str, MarketShadowOutput]
    fusion: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "sportmonks_fixture_id": self.sportmonks_fixture_id,
            "competition_key": self.competition_key,
            "generated_at": self.generated_at,
            "markets": {k: v.to_dict() for k, v in self.markets.items()},
            "fusion": self.fusion,
            "meta": self.meta,
        }
