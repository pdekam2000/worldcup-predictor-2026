"""Insurance Pick schemas (research-only)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class UncoveredScore:
    score: str
    probability: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UncoveredMassReport:
    fixture_id: int
    top_n: int
    top_n_scores: list[str]
    top_n_probability_mass: float
    primary_exact_scores: list[str]
    primary_coverage_market_key: str | None
    primary_coverage_scores: list[str]
    primary_covered_scores: list[str]
    primary_covered_probability_mass: float
    primary_uncovered_scores: list[UncoveredScore]
    primary_uncovered_probability_mass: float
    primary_coverage_ratio: float
    uncovered_result_direction: dict[str, float]
    uncovered_goal_profiles: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "top_n": self.top_n,
            "top_n_scores": list(self.top_n_scores),
            "top_n_probability_mass": self.top_n_probability_mass,
            "primary_exact_scores": list(self.primary_exact_scores),
            "primary_coverage_market_key": self.primary_coverage_market_key,
            "primary_coverage_scores": list(self.primary_coverage_scores),
            "primary_covered_scores": list(self.primary_covered_scores),
            "primary_covered_probability_mass": self.primary_covered_probability_mass,
            "primary_uncovered_scores": [s.to_dict() for s in self.primary_uncovered_scores],
            "primary_uncovered_probability_mass": self.primary_uncovered_probability_mass,
            "primary_coverage_ratio": self.primary_coverage_ratio,
            "uncovered_result_direction": dict(self.uncovered_result_direction),
            "uncovered_goal_profiles": dict(self.uncovered_goal_profiles),
        }


@dataclass
class InsuranceCandidate:
    fixture_id: int
    rank: int
    market_label: str
    market_key: str
    market_type: str
    market_parameters: dict[str, Any]
    bookmaker: str | None
    odds: float | None
    covered_uncovered_scores: list[str]
    incremental_uncovered_probability_mass: float
    primary_overlap_mass: float
    primary_overlap_ratio: float
    residual_uncovered_mass_after: float
    residual_risk_reduction: float
    implied_probability: float | None
    model_probability: float
    estimated_edge: float | None
    diversification_score: float
    insurance_score: float | None
    eligible: bool
    rejection_reason: str | None = None
    rejection_reasons: list[str] = field(default_factory=list)
    source_type: str | None = None
    odds_timestamp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InsuranceTicket:
    ticket_id: str
    rank: int
    selections: list[dict[str, Any]]
    insurance_fixture_ids: list[int]
    n_insurance_legs: int
    combined_odds: float | None
    modeled_joint_hit_probability: float
    monetary_ev: float | None
    probability_mass_utility: float
    residual_risk_reduction: float
    diversification_score: float
    overlap_penalty: float
    insurance_coupon_score: float
    inclusion_reason: str
    stake_eur: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
