from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FactorDirection = Literal["support", "oppose", "neutral"]


@dataclass
class AuditFactorContribution:
    factor_name: str
    weight_pct: float
    score: float
    contribution: float
    direction: FactorDirection
    note: str = ""


@dataclass
class DecisionConflict:
    description: str
    severity: Literal["low", "medium", "high"]


@dataclass
class DataLimitation:
    field: str
    impact: str


@dataclass
class FinalDecisionTrace:
    baseline_confidence: float
    final_confidence: float
    confidence_caps_applied: list[str] = field(default_factory=list)
    confidence_reductions: list[str] = field(default_factory=list)
    no_bet_reasons: list[str] = field(default_factory=list)
    watch_only: bool = False
    analytical_edge_note: str = ""


@dataclass
class PredictionAuditReport:
    fixture_id: int
    supported_factors: list[AuditFactorContribution] = field(default_factory=list)
    opposed_factors: list[AuditFactorContribution] = field(default_factory=list)
    neutral_factors: list[AuditFactorContribution] = field(default_factory=list)
    conflicts: list[DecisionConflict] = field(default_factory=list)
    limitations: list[DataLimitation] = field(default_factory=list)
    trace: FinalDecisionTrace | None = None
    factor_weights: dict[str, float] = field(default_factory=dict)
    market_disagreement_warnings: list[str] = field(default_factory=list)
    first_goal_player_confidence: float | None = None

    @property
    def all_contributions(self) -> list[AuditFactorContribution]:
        return self.supported_factors + self.opposed_factors + self.neutral_factors
