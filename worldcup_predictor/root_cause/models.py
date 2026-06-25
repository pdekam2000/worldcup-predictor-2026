"""Phase 58D — Root Cause Analyzer models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RootCauseRecommendation = Literal["ROOT_CAUSE_READY", "NEEDS_MORE_DATA", "NO_CLEAR_PATTERNS"]

VALID_RECOMMENDATIONS: frozenset[str] = frozenset(
    {"ROOT_CAUSE_READY", "NEEDS_MORE_DATA", "NO_CLEAR_PATTERNS"}
)

BlameLabel = Literal["helped", "hurt", "neutral", "uncertain"]


@dataclass
class MarketComparison:
    fixture_id: int
    market_id: str
    prediction: Any
    reality: Any
    confidence: float
    tier: str
    outcome: str
    league_id: int | None = None
    season_id: int | None = None
    competition_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "market_id": self.market_id,
            "prediction": self.prediction,
            "reality": self.reality,
            "confidence": self.confidence,
            "tier": self.tier,
            "outcome": self.outcome,
            "league_id": self.league_id,
            "season_id": self.season_id,
            "competition_key": self.competition_key,
        }


@dataclass
class FailureAttribution:
    fixture_id: int
    market_id: str
    failure_reason: str
    secondary_reasons: list[str] = field(default_factory=list)
    confidence: float = 0.5
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "market_id": self.market_id,
            "failure_reason": self.failure_reason,
            "secondary_reasons": self.secondary_reasons,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass
class ComponentBlame:
    component_id: str
    label: BlameLabel
    weight: float
    component_confidence: float
    prediction: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "label": self.label,
            "weight": self.weight,
            "component_confidence": self.component_confidence,
            "prediction": self.prediction,
        }


@dataclass
class KnowledgeRecord:
    fixture_id: int
    market: str
    failure_reason: str
    component_scores: dict[str, str]
    recommended_action: str
    confidence: float
    league_id: int | None = None
    season_id: int | None = None
    patterns: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "market": self.market,
            "failure_reason": self.failure_reason,
            "component_scores": self.component_scores,
            "recommended_action": self.recommended_action,
            "confidence": self.confidence,
            "league_id": self.league_id,
            "season_id": self.season_id,
            "patterns": self.patterns,
            "meta": self.meta,
        }
