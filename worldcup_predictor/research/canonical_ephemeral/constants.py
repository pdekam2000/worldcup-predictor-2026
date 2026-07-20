"""CANONICAL_RESEARCH_EPHEMERAL — constants and protected tables."""

from __future__ import annotations

EXECUTION_MODE = "CANONICAL_RESEARCH_EPHEMERAL"

# Canonical tables that must not be written during ephemeral research execution.
PROTECTED_TABLES = frozenset(
    {
        "worldcup_stored_predictions",
        "ecse_prediction_snapshots",
        "ecse_prediction_evaluations",
        "frozen_predictions",
        "exact_score_rankings",
        "excluded_candidates",
        "actual_results",
        "market_evaluations",
        "prediction_context",
        "evaluation_batches",
        "freeze_quarantine",
        "forward_evaluation_runs",
        # Tier B structured shadow freeze store (also non-ephemeral for this experiment)
        "tier_b_shadow_predictions",
    }
)

PROTECTED_WRITE_OPS = frozenset({"INSERT", "UPDATE", "DELETE", "REPLACE"})
