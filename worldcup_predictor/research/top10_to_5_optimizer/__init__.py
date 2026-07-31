"""Top10-to-5 Profit-Aware Coverage Optimizer — research-only.

Compresses model Top10 exact-score outcomes into exactly five betting
selections (3 Exact Score + 2 Smart Coverage Markets) using real odds.

Hard invariants:
  - research_only / owner_only / NOT DEPLOYED
  - Never mutates canonical WDE / ECSE / freezes
  - Never promotes Exact V2
  - Never fabricates odds or markets
  - Does not auto-execute 125-ticket coupons
  - Does not modify Coverage Optimizer or Insurance Optimizer
"""

from __future__ import annotations

RESEARCH_ONLY = True
OWNER_ONLY = True
NOT_DEPLOYED = True
PHASE_NAME = "TOP10_TO_5_PROFIT_AWARE_COVERAGE_OPTIMIZER"
STATUS_COMPLETE = "TOP10_TO_5_PROFIT_AWARE_OPTIMIZER_COMPLETE"
STATUS_HOLD = "TOP10_TO_5_PROFIT_AWARE_OPTIMIZER_HOLD"
STATUS_RESEARCH_MORE = "TOP10_TO_5_PROFIT_AWARE_OPTIMIZER_RESEARCH_MORE"
BASELINE_COMMIT = "70530d3"
PACKAGE_VERSION = "t10to5-1.0.0"

__all__ = [
    "RESEARCH_ONLY",
    "OWNER_ONLY",
    "NOT_DEPLOYED",
    "PHASE_NAME",
    "STATUS_COMPLETE",
    "STATUS_HOLD",
    "STATUS_RESEARCH_MORE",
    "BASELINE_COMMIT",
    "PACKAGE_VERSION",
]
