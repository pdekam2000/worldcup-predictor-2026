"""Bet Portfolio Manager — research-only capital decision layer.

Architecture note:
- Does NOT duplicate OBPE market selection (`optimal_betting_portfolio_engine`).
- Does NOT modify Coverage/Insurance Optimizer, WDE, ECSE, or freezes.
- Consumes prediction / BCO outputs read-only and decides whether / how much to invest.
"""

from __future__ import annotations

from worldcup_predictor.research.bet_portfolio_manager.constants import (
    PHASE_NAME,
    STATUS_COMPLETE,
)

__all__ = ["PHASE_NAME", "STATUS_COMPLETE"]
