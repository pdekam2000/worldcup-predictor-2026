"""Paper betting simulator — Phase A18 (virtual only)."""

from worldcup_predictor.paper_betting.service import (
    create_or_update_account,
    get_account,
    list_bets,
    place_bet,
    place_combo_bets,
    reset_account_month,
    settle_pending_bets,
)

__all__ = [
    "create_or_update_account",
    "get_account",
    "list_bets",
    "place_bet",
    "place_combo_bets",
    "reset_account_month",
    "settle_pending_bets",
]
