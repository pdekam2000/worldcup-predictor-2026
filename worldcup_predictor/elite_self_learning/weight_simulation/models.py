"""Phase 58B — weight simulation models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SimulationRecommendation = Literal["LEARNING_SIMULATION_READY", "NEEDS_MORE_DATA", "NO_IMPROVEMENT"]

VALID_SIMULATION_RECOMMENDATIONS: frozenset[str] = frozenset(
    {"LEARNING_SIMULATION_READY", "NEEDS_MORE_DATA", "NO_IMPROVEMENT"}
)

REPLAY_WINDOWS: tuple[int, ...] = (100, 500, 1000)

ApprovalStatus = Literal["ACCEPT", "REJECT", "HOLD", "INSUFFICIENT_DATA"]


@dataclass(frozen=True)
class WeightSnapshot:
    snapshot_id: str
    label: str
    market_id: str
    weights: dict[str, float]
    source: str
    immutable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "label": self.label,
            "market_id": self.market_id,
            "weights": self.weights,
            "source": self.source,
            "immutable": self.immutable,
        }


@dataclass
class ReplayMetrics:
    window: int
    market_id: str
    weight_label: str
    n: int
    accuracy: float
    brier: float
    ece: float
    roi_proxy: float
    mean_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": self.window,
            "market_id": self.market_id,
            "weight_label": self.weight_label,
            "n": self.n,
            "accuracy": self.accuracy,
            "brier": self.brier,
            "ece": self.ece,
            "roi_proxy": self.roi_proxy,
            "mean_confidence": self.mean_confidence,
        }


@dataclass
class WindowComparison:
    window: int
    market_id: str
    old: ReplayMetrics
    new: ReplayMetrics
    delta_accuracy: float
    delta_brier: float
    delta_ece: float
    delta_roi_proxy: float
    picks_changed: int
    bootstrap_p_improve: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": self.window,
            "market_id": self.market_id,
            "old": self.old.to_dict(),
            "new": self.new.to_dict(),
            "delta_accuracy": self.delta_accuracy,
            "delta_brier": self.delta_brier,
            "delta_ece": self.delta_ece,
            "delta_roi_proxy": self.delta_roi_proxy,
            "picks_changed": self.picks_changed,
            "bootstrap_p_improve": self.bootstrap_p_improve,
        }


@dataclass
class ComponentLearningReport:
    component_id: str
    market_id: str
    current_weight: float
    recommended_weight: float
    expected_gain_accuracy: float
    expected_gain_brier: float
    confidence: float
    approval_status: ApprovalStatus
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "market_id": self.market_id,
            "current_weight": self.current_weight,
            "recommended_weight": self.recommended_weight,
            "expected_gain_accuracy": self.expected_gain_accuracy,
            "expected_gain_brier": self.expected_gain_brier,
            "confidence": self.confidence,
            "approval_status": self.approval_status,
            "reason": self.reason,
        }
