"""Structured models for Phase 46 — Final Decision Fusion Engine V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

QualityBand = Literal["Weak", "Moderate", "Strong", "Very Strong"]


@dataclass
class AgentSignalRow:
    agent_key: str
    label: str
    home_signal: float = 0.0
    away_signal: float = 0.0
    draw_signal: float = 0.0
    over25_signal: float = 0.0
    under25_signal: float = 0.0
    weight: float = 1.0
    quality_multiplier: float = 1.0
    lean_1x2: str = "neutral"
    lean_ou: str = "neutral"

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_key": self.agent_key,
            "label": self.label,
            "home_signal": round(self.home_signal, 1),
            "away_signal": round(self.away_signal, 1),
            "draw_signal": round(self.draw_signal, 1),
            "over25_signal": round(self.over25_signal, 1),
            "under25_signal": round(self.under25_signal, 1),
            "weight": round(self.weight, 2),
            "quality_multiplier": round(self.quality_multiplier, 2),
            "lean_1x2": self.lean_1x2,
            "lean_ou": self.lean_ou,
        }


@dataclass
class SignalMatrix:
    home_signal: float = 0.0
    away_signal: float = 0.0
    draw_signal: float = 0.0
    over25_signal: float = 0.0
    under25_signal: float = 0.0
    agents: list[AgentSignalRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "home_signal": round(self.home_signal, 1),
            "away_signal": round(self.away_signal, 1),
            "draw_signal": round(self.draw_signal, 1),
            "over25_signal": round(self.over25_signal, 1),
            "under25_signal": round(self.under25_signal, 1),
            "agents": [a.to_dict() for a in self.agents],
        }


@dataclass
class FusionConflict:
    description: str
    severity: Literal["low", "medium", "high"] = "medium"
    agents: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FinalDecisionFusionReport:
    baseline_prediction: dict[str, Any] = field(default_factory=dict)
    fusion_prediction: dict[str, Any] = field(default_factory=dict)
    signal_matrix: SignalMatrix = field(default_factory=SignalMatrix)
    consensus_strength: float = 50.0
    decision_quality_score: float = 50.0
    decision_quality_band: QualityBand = "Moderate"
    conflicts: list[FusionConflict] = field(default_factory=list)
    conflict_resolution_summary: str = ""
    risk_flags: list[str] = field(default_factory=list)
    confidence_adjustment: float = 0.0
    final_summary: str = ""
    version: str = "v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_prediction": self.baseline_prediction,
            "fusion_prediction": self.fusion_prediction,
            "signal_matrix": self.signal_matrix.to_dict(),
            "consensus_strength": round(self.consensus_strength, 1),
            "decision_quality_score": round(self.decision_quality_score, 1),
            "decision_quality_band": self.decision_quality_band,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "conflict_resolution_summary": self.conflict_resolution_summary,
            "risk_flags": self.risk_flags,
            "confidence_adjustment": round(self.confidence_adjustment, 2),
            "final_summary": self.final_summary,
            "version": self.version,
        }
