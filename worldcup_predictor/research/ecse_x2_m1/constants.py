"""PHASE ECSE-X2-M1 — BTTS × OU quadrant geometry for exact-score filtering."""

from __future__ import annotations

PHASE = "ECSE-X2-M1"
METHOD_VERSION = "ECSE-X2-M1-v1"
TABLE_NAME = "ecse_score_distributions_m1"
BASELINE_TABLE = "ecse_score_distributions"

QUADRANTS = ("yes_over", "yes_under", "no_under", "no_over")

# Canonical score-world exemplars from ECSE-X1 hypothesis (used for documentation / soft priors).
QUADRANT_EXEMPLARS: dict[str, frozenset[str]] = {
    "yes_over": frozenset({"2-1", "1-2", "2-2", "3-1"}),
    "yes_under": frozenset({"1-1"}),
    "no_under": frozenset({"0-0", "1-0", "0-1", "2-0"}),
    "no_over": frozenset({"3-0", "0-3", "4-0", "0-4"}),
}

SPECIAL_BTTS_YES_MIN = 0.58
SPECIAL_UNDER_25_MIN = 0.55
