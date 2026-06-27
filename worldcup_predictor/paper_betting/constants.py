"""Paper betting constants — Phase A18."""

from __future__ import annotations

BET_STATUS_PENDING = "pending"
BET_STATUS_WON = "won"
BET_STATUS_LOST = "lost"
BET_STATUS_VOID = "void"
BET_STATUS_PARTIAL = "partial"

FREE_DAILY_BET_LIMIT = 5

MARKET_EVAL_COLUMN: dict[str, str] = {
    "1x2": "market_1x2_status",
    "match_winner": "market_1x2_status",
    "over_under_2_5": "market_ou_status",
    "over_under_25": "market_ou_status",
    "btts": "market_btts_status",
    "double_chance": "market_dc_status",
    "ht_result": "market_ht_status",
    "halftime": "market_ht_status",
    "correct_score": "market_cs_status",
    "first_goal_team": "market_fg_team_status",
    "goalscorer": "market_goalscorer_status",
    "goal_minute": "market_goal_minute_status",
}
