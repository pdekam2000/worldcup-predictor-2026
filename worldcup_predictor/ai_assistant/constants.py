"""AI Assistant constants — Phase A19."""

from __future__ import annotations

WATCHLIST_TYPES = ("competition", "team", "player", "fixture", "market")

NOTIFICATION_CATEGORIES = (
    "prediction",
    "quality",
    "combo",
    "paper_betting",
    "system",
    "archive",
)

ALERT_TYPES = (
    "quality_increase",
    "quality_decrease",
    "best_pick_change",
    "lineup_published",
    "odds_movement",
    "egie_prediction_change",
    "safe_combo_available",
    "prediction_ready",
    "match_final_hours",
    "paper_bet_settled",
    "portfolio_updated",
    "roi_milestone",
    "drawdown_warning",
    "archive_accuracy_update",
    "quality_overnight",
)

DEFAULT_PREFERENCES: dict = {
    "alert_frequency": "normal",  # low, normal, high
    "favorite_leagues": [],
    "favorite_teams": [],
    "min_bet_quality": 45,
    "min_combo_type": "balanced",
    "quiet_hours_start": None,
    "quiet_hours_end": None,
    "timezone": "UTC",
    "channels": ["in_app"],
}

QUALITY_CHANGE_THRESHOLD = 5.0
ODDS_MOVEMENT_THRESHOLD_PCT = 8.0
DRAWDOWN_WARNING_PCT = 15.0
ROI_MILESTONE_STEPS = (5, 10, 20, 50)
DEDUP_WINDOW_HOURS = 6
