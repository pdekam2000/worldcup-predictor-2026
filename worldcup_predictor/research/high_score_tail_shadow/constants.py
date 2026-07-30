"""High-score tail shadow research — constants (shadow-only, non-canonical)."""

from __future__ import annotations

PHASE = "HIGH-SCORE-TAIL-SHADOW-1"
SHADOW_ONLY = True
PUBLIC_PUBLISH = False
CANONICAL_MAX_GOALS = 7  # production ECSE-1D-B grid
ARTIFACT_SUBDIR = "high_score_tail_research"

# Forward-shadow promotion gates (from owner brief)
FORWARD_MIN_TOTAL_DC = 150
FORWARD_MIN_HIGH_SCORE_RISK = 75
FORWARD_MIN_GLOBAL_PROMOTION = 250

# Guardrails
MAX_LOW_SCORE_TOP5_REGRESSION_PP = 3.0
MAX_GLOBAL_TOP5_REGRESSION_PP = 2.0

LOW_TOTAL = {0, 1}
MED_TOTAL = {2, 3}
HIGH_TOTAL = {4}
EXTREME_TOTAL = set(range(5, 20))

OVER_RANKED_CANDIDATES = ("0-0", "1-0", "0-1", "1-1", "2-0", "0-2")
UNDER_RANKED_CANDIDATES = (
    "2-1", "1-2", "2-2", "3-0", "0-3", "3-1", "1-3", "3-2", "2-3", "4-0", "0-4"
)

REGIME_LOW = "LOW_SCORE"
REGIME_HIGH = "HIGH_SCORE"
REGIME_UNCLEAR = "UNCLEAR"
