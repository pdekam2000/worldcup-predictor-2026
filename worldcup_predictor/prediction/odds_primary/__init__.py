"""Odds-primary shadow scoreline engine (Phase 16 — shadow only)."""

from worldcup_predictor.prediction.odds_primary.engine import OddsPrimaryScorelineEngine
from worldcup_predictor.prediction.odds_primary.models import (
    OddsPrimaryMode,
    OddsPrimaryResult,
)

__all__ = [
    "OddsPrimaryMode",
    "OddsPrimaryResult",
    "OddsPrimaryScorelineEngine",
]
