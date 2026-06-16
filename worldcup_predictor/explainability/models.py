"""Structured models for Phase 41 — Prediction Explainability & Final Report V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

RiskBand = Literal["Very Low", "Low", "Moderate", "High", "Very High"]
AgreementBand = Literal["Very Low", "Low", "Moderate", "Strong", "Very Strong"]


@dataclass
class AgentContribution:
    agent_key: str
    label: str
    raw_score: float
    influence_pct: float
    direction: Literal["positive", "negative", "neutral"]
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OutcomeExplanation:
    outcome: str
    supported: bool
    explanation: str
    strength: Literal["strong", "moderate", "weak"]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgreementAnalysis:
    agreement_score: float
    agreement_band: AgreementBand
    supporting_agents: int
    opposing_agents: int
    neutral_agents: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConflictAnalysis:
    conflict_score: float
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConfidenceExplanation:
    score: float
    level: str
    boosters: list[str] = field(default_factory=list)
    reducers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiskAnalysis:
    risk_level: RiskBand
    top_risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionTimelineStep:
    agent_label: str
    verdict: str
    lean: Literal["home", "away", "draw", "over", "under", "neutral"]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SignalDiversityExplanation:
    fusion_diversity_score: float
    independent_signals: list[str] = field(default_factory=list)
    correlated_signals: list[str] = field(default_factory=list)
    independent_count: int = 0
    correlated_count: int = 0
    redundant_agents: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FinalReportV2:
    prediction: dict[str, Any]
    confidence: ConfidenceExplanation
    agreement: AgreementAnalysis
    conflicts: ConflictAnalysis
    risk_analysis: RiskAnalysis
    agent_contributions: list[AgentContribution]
    decision_timeline: list[DecisionTimelineStep]
    outcome_explanations: list[OutcomeExplanation]
    top_positive_factors: list[str]
    top_negative_factors: list[str]
    executive_summary: str
    fusion_report: dict[str, Any] | None = None
    api_sports_context: dict[str, Any] | None = None
    signal_diversity: dict[str, Any] | None = None
    version: str = "v2"

    def to_dict(self) -> dict[str, Any]:
        out = {
            "prediction": self.prediction,
            "confidence": self.confidence.to_dict(),
            "agreement": self.agreement.to_dict(),
            "conflicts": self.conflicts.to_dict(),
            "risk_analysis": self.risk_analysis.to_dict(),
            "agent_contributions": [c.to_dict() for c in self.agent_contributions],
            "decision_timeline": [s.to_dict() for s in self.decision_timeline],
            "outcome_explanations": [e.to_dict() for e in self.outcome_explanations],
            "top_positive_factors": self.top_positive_factors,
            "top_negative_factors": self.top_negative_factors,
            "executive_summary": self.executive_summary,
            "version": self.version,
        }
        if self.fusion_report:
            out["fusion_report"] = self.fusion_report
        if self.api_sports_context:
            out["api_sports_context"] = self.api_sports_context
        if self.signal_diversity:
            out["signal_diversity"] = self.signal_diversity
        return out
