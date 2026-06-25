"""Domain models for hybrid per-market confidence (Phase 52D)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ConfidenceTier = Literal["A", "B", "C", "D"]


@dataclass
class HybridConfidenceScores:
    conf_team: float
    conf_range: float
    conf_minute: float
    data_completeness: float
    team_probability_gap: float
    abstention_distance: float
    survival_range_margin: float
    hazard_concentration: float
    timing_entropy_inverse: float
    historical_team_reliability: float
    historical_range_reliability: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HybridConfidenceTiers:
    team_tier: ConfidenceTier
    range_tier: ConfidenceTier
    minute_tier: ConfidenceTier
    display_tier: ConfidenceTier

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HybridConfidenceUI:
    team_label: str
    team_badge: str
    range_label: str
    range_show_probability_bar: bool
    minute_label: str
    minute_badge: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HybridConfidenceResult:
    fixture_id: int
    competition_key: str
    model_version: str
    shadow_mode: bool
    scores: HybridConfidenceScores
    tiers: HybridConfidenceTiers
    ui: HybridConfidenceUI
    legacy_confidence_score: float | None = None
    components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "competition_key": self.competition_key,
            "model_version": self.model_version,
            "shadow_mode": self.shadow_mode,
            "conf_team": self.scores.conf_team,
            "conf_range": self.scores.conf_range,
            "conf_minute": self.scores.conf_minute,
            "scores": self.scores.to_dict(),
            "tiers": self.tiers.to_dict(),
            "ui": self.ui.to_dict(),
            "legacy_confidence_score": self.legacy_confidence_score,
            "components": self.components,
        }
