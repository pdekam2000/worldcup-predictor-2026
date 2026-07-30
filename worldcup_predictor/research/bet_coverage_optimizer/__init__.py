"""Bet Coverage Optimizer — research-only, owner-only.

Converts Top-N exact-score distributions + REAL bookmaker markets into
exactly four selections per fixture (3 Exact Score + 1 Smart Coverage).

Hard invariants:
  - Never mutates canonical WDE / ECSE / BTTS / O/U formulas or freezes.
  - Never invents odds or markets.
  - Never promotes shadow models.
  - research_only=true, owner_only=true, final_decision_authority=false.
"""

from __future__ import annotations

RECOMMENDATION_VERSION = "bco-1.0.0"
RESEARCH_ONLY = True
OWNER_ONLY = True
PUBLIC_VISIBLE = False
FINAL_DECISION_AUTHORITY = False
STATUS_COVERAGE_UNAVAILABLE = "COVERAGE_MARKET_UNAVAILABLE"
STATUS_OK = "OK"

__all__ = [
    "RECOMMENDATION_VERSION",
    "RESEARCH_ONLY",
    "OWNER_ONLY",
    "STATUS_COVERAGE_UNAVAILABLE",
    "STATUS_OK",
]
