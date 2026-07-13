"""Constants for Last-8 team goal form shadow research."""

from __future__ import annotations

# Suggested starting recency weights (most recent first); auditable, not hardcoded in logic paths.
DEFAULT_RECENCY_WEIGHTS: tuple[float, ...] = (1.00, 0.90, 0.82, 0.74, 0.67, 0.60, 0.54, 0.49)

MATCHES_REQUESTED = 8

COVERAGE_FULL = "FULL_8_MATCH_COVERAGE"
COVERAGE_PARTIAL_5_7 = "PARTIAL_5_TO_7"
COVERAGE_LIMITED_3_4 = "LIMITED_3_TO_4"
COVERAGE_INSUFFICIENT = "INSUFFICIENT_UNDER_3"
COVERAGE_MAPPING_BLOCKED = "MAPPING_BLOCKED"
COVERAGE_RESULT_MISSING = "RESULT_DATA_MISSING"

FRIENDLY_KEY_PATTERNS: tuple[str, ...] = (
    "friendly",
    "friendlies",
    "club friendlies",
    "international friendlies",
)

# Promotion research gates (not automatic production approval).
PROMOTION_MIN_PAIRED_FIXTURES = 100
PROMOTION_MIN_LEAGUE_FIXTURES = 30
PROMOTION_TOP5_LIFT_PP = 3.0
PROMOTION_TOP3_MAX_DEGRADATION_PP = 1.0

SHADOW_LABEL = "SHADOW_ONLY"
PUBLIC_PUBLISH = False
