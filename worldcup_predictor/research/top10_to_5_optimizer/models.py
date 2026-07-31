"""Typed helpers / lightweight models for Top10-to-5."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScoreProb:
    score: str
    probability: float
    rank: int | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketCandidate:
    market_type: str
    market_parameters: dict[str, Any]
    label: str
    decimal_odds: float | None
    bookmaker: str | None = None
    source_type: str | None = None
    freshness: str | None = None
    market_key: str = ""
    modeled_probability: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_type": self.market_type,
            "market_parameters": dict(self.market_parameters),
            "label": self.label,
            "decimal_odds": self.decimal_odds,
            "bookmaker": self.bookmaker,
            "source_type": self.source_type,
            "freshness": self.freshness,
            "market_key": self.market_key,
            "modeled_probability": self.modeled_probability,
            "odds_available": self.decimal_odds is not None and float(self.decimal_odds) > 1.0,
        }


@dataclass
class StakePlan:
    stakes: dict[str, float]
    total_budget: float
    mode: str
    rounding_step: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FixtureRecommendation:
    fixture_id: int
    status: str
    exact_scores: list[str]
    coverage_markets: list[dict[str, Any]]
    stakes: dict[str, float]
    matrix: list[dict[str, Any]]
    metrics: dict[str, Any]
    blockers: list[str] = field(default_factory=list)
    evidence_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "recommendation_status": self.status,
            "exact_score_1": self.exact_scores[0] if len(self.exact_scores) > 0 else None,
            "exact_score_2": self.exact_scores[1] if len(self.exact_scores) > 1 else None,
            "exact_score_3": self.exact_scores[2] if len(self.exact_scores) > 2 else None,
            "coverage_market_1": self.coverage_markets[0] if len(self.coverage_markets) > 0 else None,
            "coverage_market_2": self.coverage_markets[1] if len(self.coverage_markets) > 1 else None,
            "stakes": self.stakes,
            "metrics": self.metrics,
            "blocker_reasons": self.blockers,
            "evidence_hash": self.evidence_hash,
            "coverage_matrix": self.matrix,
            "research_only": True,
            "not_deployed": True,
        }
