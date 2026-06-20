"""Trace promotion adapters — Phase 24A / 24B / 24C."""

from worldcup_predictor.promotion.expected_lineup_adapter import (
    apply_lineup_promotion_to_factor,
    compute_expected_lineup_promotion,
)
from worldcup_predictor.promotion.models import (
    ExpectedLineupPromotionResult,
    SportmonksPredictionPromotionResult,
    TournamentContextPromotionResult,
    XGPromotionResult,
)
from worldcup_predictor.promotion.sportmonks_prediction_adapter import (
    compute_sportmonks_prediction_promotion,
)
from worldcup_predictor.promotion.tournament_context_adapter import (
    apply_context_promotion_to_factor,
    compute_tournament_context_promotion,
)
from worldcup_predictor.promotion.xg_promotion_adapter import (
    apply_xg_promotion_to_factor,
    compute_xg_promotion,
)

__all__ = [
    "ExpectedLineupPromotionResult",
    "SportmonksPredictionPromotionResult",
    "TournamentContextPromotionResult",
    "XGPromotionResult",
    "apply_context_promotion_to_factor",
    "apply_lineup_promotion_to_factor",
    "apply_xg_promotion_to_factor",
    "compute_expected_lineup_promotion",
    "compute_sportmonks_prediction_promotion",
    "compute_tournament_context_promotion",
    "compute_xg_promotion",
]
