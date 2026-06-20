"""Promotion adapter models — Phase 24A / 24B."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

PromotionMode = Literal["off", "shadow", "gated"]


@dataclass
class TournamentContextPromotionResult:
    context_promotion_active: bool = False
    context_delta_score: float = 0.0
    context_delta_edge: float = 0.0
    context_promotion_reason: str = "promotion_off"
    context_promotion_confidence: float = 0.0
    must_win_influence: float = 0.0
    rotation_context_influence: float = 0.0
    draw_acceptability_influence: float = 0.0
    confidence_delta: float = 0.0
    tactics_trace_notes: str = ""
    tactics_over_trace_delta: float = 0.0
    baseline_motivation_score: float = 0.0
    promoted_motivation_score: float = 0.0
    mode: PromotionMode = "off"
    gate_passed: bool = False
    applied: bool = False
    version: str = "24b"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class XGPromotionResult:
    xg_promotion_active: bool = False
    xg_delta_score: float = 0.0
    xg_delta_over: float = 0.0
    xg_promotion_reason: str = "promotion_off"
    xg_promotion_confidence: float = 0.0
    baseline_tactics_score: float = 0.0
    promoted_tactics_score: float = 0.0
    mode: PromotionMode = "off"
    gate_passed: bool = False
    applied: bool = False
    version: str = "24c-xg"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SportmonksPredictionPromotionResult:
    sportmonks_promotion_active: bool = False
    sportmonks_confidence_delta: float = 0.0
    sportmonks_disagreement_signal: str = ""
    sportmonks_promotion_reason: str = "promotion_off"
    no_bet_review_trace: bool = False
    internal_lean: str = ""
    sportmonks_lean: str = ""
    conflict_level: str = "low"
    mode: PromotionMode = "off"
    gate_passed: bool = False
    applied: bool = False
    version: str = "24c-sm"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExpectedLineupPromotionResult:
    lineup_promotion_active: bool = False
    lineup_delta_score: float = 0.0
    lineup_delta_edge: float = 0.0
    lineup_promotion_reason: str = "promotion_off"
    lineup_promotion_confidence: float = 0.0
    confidence_delta: float = 0.0
    expected_vs_confirmed_history: dict[str, Any] = field(default_factory=dict)
    baseline_lineup_score: float = 0.0
    promoted_lineup_score: float = 0.0
    mode: PromotionMode = "off"
    gate_passed: bool = False
    applied: bool = False
    version: str = "24a"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
