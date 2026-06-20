from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

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
    lineup_promotion_active: bool = False
    lineup_delta_score: float = 0.0
    lineup_promotion_reason: str = ""
    lineup_promotion_confidence: float = 0.0
    expected_vs_confirmed_history: dict[str, Any] = field(default_factory=dict)
    context_promotion_active: bool = False
    context_delta_score: float = 0.0
    context_promotion_reason: str = ""
    context_promotion_confidence: float = 0.0
    must_win_influence: float = 0.0
    rotation_context_influence: float = 0.0
    draw_acceptability_influence: float = 0.0
    tactics_trace_notes: str = ""
    tactics_over_trace_delta: float = 0.0
    xg_promotion_active: bool = False
    xg_delta_score: float = 0.0
    xg_promotion_reason: str = ""
    xg_promotion_confidence: float = 0.0
    sportmonks_promotion_active: bool = False
    sportmonks_confidence_delta: float = 0.0
    sportmonks_disagreement_signal: str = ""
    sportmonks_promotion_reason: str = ""
    sportmonks_no_bet_review_trace: bool = False
    combined_promotion_confidence_delta: float = 0.0


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
