"""Phase 5 constants — long-term scientific validation (research-only)."""

from __future__ import annotations

PHASE_NAME = "BET_COVERAGE_OPTIMIZER_PHASE5_LONG_TERM_VALIDATION"
STATUS_VALIDATED = "BET_COVERAGE_OPTIMIZER_PHASE5_LONG_TERM_VALIDATED"
RESEARCH_ONLY = True
OWNER_ONLY = True
NO_PRODUCTION_DEPLOY = True
MIN_HISTORICAL_FIXTURES = 1000

ODDS_BUCKETS = (
    (1.50, 1.80, "1.50-1.80"),
    (1.80, 2.10, "1.80-2.10"),
    (2.10, 2.50, "2.10-2.50"),
    (2.50, 3.00, "2.50-3.00"),
    (3.00, 99.0, "3.00+"),
)

# Prematch CSV fields → settlement markets (real bookmaker odds only)
RAW_MARKET_SPECS: tuple[tuple[str, str, dict, str], ...] = (
    ("BTTS Yes", "btts", {"side": "yes"}, "oddsFT_BTTS_Yes"),
    ("BTTS No", "btts", {"side": "no"}, "oddsFT_BTTS_No"),
    ("Over 1.5", "over_under", {"direction": "over", "line": 1.5}, "oddsFT_Over_1_5"),
    ("Over 2.5", "over_under", {"direction": "over", "line": 2.5}, "oddsFT_Over_2_5"),
    ("Under 2.5", "over_under", {"direction": "under", "line": 2.5}, "oddsFT_Under_2_5"),
    ("Under 3.5", "over_under", {"direction": "under", "line": 3.5}, "oddsFT_Under_3_5"),
    ("Double Chance 1X", "double_chance", {"side": "1x"}, "oddsFT_1X"),
    ("Double Chance X2", "double_chance", {"side": "x2"}, "oddsFT_X2"),
    ("Double Chance 12", "double_chance", {"side": "12"}, "oddsFT_12"),
    ("Home Win", "1x2", {"result": "home"}, "oddsFT_1"),
    ("Draw", "1x2", {"result": "draw"}, "oddsFT_X"),
    ("Away Win", "1x2", {"result": "away"}, "oddsFT_2"),
)
