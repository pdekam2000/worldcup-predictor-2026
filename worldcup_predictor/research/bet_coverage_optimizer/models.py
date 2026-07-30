"""Additive schemas for Bet Coverage Optimizer (research-only)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ScoreEntry:
    score: str
    probability: float
    rank: int | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelTopScores:
    model_id: str
    scores: list[ScoreEntry]
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "weight": self.weight,
            "scores": [s.to_dict() for s in self.scores],
        }


@dataclass
class ScoringWeights:
    covered_mass: float = 0.35
    non_exact_mass: float = 0.20
    exact_overlap_mass: float = 0.15
    estimated_edge: float = 0.20
    log_odds: float = 0.10
    min_odds: float = 1.55
    stale_penalty: float = 1.0
    redundant_penalty: float = 0.35
    narrow_mass_penalty: float = 0.25
    narrow_mass_threshold: float = 0.05

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CoverageMarketEvaluation:
    fixture_id: int
    bookmaker: str | None
    provider: str | None
    market_key: str
    market_label: str
    market_type: str
    market_parameters: dict[str, Any]
    odds: float | None
    odds_timestamp: str | None
    odds_age_seconds: float | None
    odds_freshness_status: str | None
    target_scores: list[str]
    covered_scores: list[str]
    covered_probability_mass: float
    exact_overlap_scores: list[str]
    non_exact_covered_scores: list[str]
    exact_overlap_probability_mass: float
    non_exact_coverage_probability_mass: float
    estimated_model_probability: float
    implied_probability: float | None
    estimated_edge: float | None
    coverage_score: float | None
    eligible: bool
    rejection_reasons: list[str] = field(default_factory=list)
    evidence_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExactSelection:
    score: str
    consensus_count: int
    weighted_probability: float
    canonical_rank: int | None
    exact_v2_rank: int | None
    selection_id: str
    label: str
    odds: float | None = None
    odds_freshness_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CoverageRecommendation:
    fixture_id: int
    model_snapshot_hash: str
    selected_exact_scores: list[ExactSelection]
    selected_coverage_market: CoverageMarketEvaluation | None
    top8_scores: list[ScoreEntry]
    total_top8_probability_mass: float
    covered_top8_scores: list[str]
    uncovered_top8_scores: list[str]
    generated_at: str
    research_only: bool = True
    owner_only: bool = True
    recommendation_version: str = "bco-1.0.0"
    status: str = "OK"
    blockers: list[str] = field(default_factory=list)
    rejected_candidates: list[CoverageMarketEvaluation] = field(default_factory=list)
    candidate_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "model_snapshot_hash": self.model_snapshot_hash,
            "selected_exact_scores": [s.to_dict() for s in self.selected_exact_scores],
            "selected_coverage_market": (
                self.selected_coverage_market.to_dict() if self.selected_coverage_market else None
            ),
            "fourth_selection": (
                self.selected_coverage_market.to_dict() if self.selected_coverage_market else None
            ),
            "top8_scores": [s.to_dict() for s in self.top8_scores],
            "total_top8_probability_mass": self.total_top8_probability_mass,
            "covered_top8_scores": list(self.covered_top8_scores),
            "uncovered_top8_scores": list(self.uncovered_top8_scores),
            "generated_at": self.generated_at,
            "research_only": self.research_only,
            "owner_only": self.owner_only,
            "recommendation_version": self.recommendation_version,
            "status": self.status,
            "blockers": list(self.blockers),
            "rejected_candidates": [c.to_dict() for c in self.rejected_candidates],
            "candidate_count": self.candidate_count,
        }
