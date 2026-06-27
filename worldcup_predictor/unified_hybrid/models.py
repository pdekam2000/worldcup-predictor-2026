"""Unified hybrid prediction models — Phase 61."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UnifiedMarketPick:
    market_id: str
    market_label: str
    selection: str | None
    probability: float | None = None
    confidence: float | None = None
    tier: str | None = None
    risk_level: str | None = None
    value_signal: str | None = None
    odds_movement: str | None = None
    source_engine: str = "hybrid"
    engine_agreement: str = "agree"
    explanation: str | None = None
    component_contributions: dict[str, Any] = field(default_factory=dict)
    status: str = "available"
    reason: str | None = None


@dataclass
class UnifiedPredictionOutput:
    fixture_id: int
    competition_key: str | None
    home_team: str
    away_team: str
    kickoff_utc: str | None
    fixture_status: str | None
    markets: dict[str, UnifiedMarketPick]
    best_tip: UnifiedMarketPick | None
    combo_candidates: dict[str, list[dict[str, Any]]]
    overall_confidence: float | None
    overall_tier: str | None
    data_quality_score: float | None
    feature_freshness: dict[str, Any]
    missing_data_warnings: list[str]
    component_contributions: dict[str, Any]
    engine_versions: dict[str, str]
    compare_mode: dict[str, Any] | None = None
    disclaimer: str = "Research and analysis only — not betting advice."

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "competition_key": self.competition_key,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "kickoff_utc": self.kickoff_utc,
            "fixture_status": self.fixture_status,
            "markets": {k: _market_to_dict(v) for k, v in self.markets.items()},
            "best_tip": _market_to_dict(self.best_tip) if self.best_tip else None,
            "combo_candidates": self.combo_candidates,
            "overall_confidence": self.overall_confidence,
            "overall_tier": self.overall_tier,
            "data_quality_score": self.data_quality_score,
            "feature_freshness": self.feature_freshness,
            "missing_data_warnings": self.missing_data_warnings,
            "component_contributions": self.component_contributions,
            "engine_versions": self.engine_versions,
            "compare_mode": self.compare_mode,
            "disclaimer": self.disclaimer,
            "unified_engine_version": "61-v1",
        }


def _market_to_dict(pick: UnifiedMarketPick | None) -> dict[str, Any] | None:
    if pick is None:
        return None
    return {
        "market_id": pick.market_id,
        "market_label": pick.market_label,
        "selection": pick.selection,
        "probability": pick.probability,
        "confidence": pick.confidence,
        "tier": pick.tier,
        "risk_level": pick.risk_level,
        "value_signal": pick.value_signal,
        "odds_movement": pick.odds_movement,
        "source_engine": pick.source_engine,
        "engine_agreement": pick.engine_agreement,
        "explanation": pick.explanation,
        "component_contributions": pick.component_contributions,
        "status": pick.status,
        "reason": pick.reason,
    }
