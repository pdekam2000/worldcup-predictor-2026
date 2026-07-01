"""Constants for owner daily prediction cycle."""

from __future__ import annotations

from pathlib import Path

PHASE = "DAILY-OWNER-1"
GENERATED_BY = "owner_daily_predictions"

DAILY_SUPPORTED_COMPETITIONS: tuple[str, ...] = (
    "world_cup_2026",
    "champions_league",
    "europa_league",
    "conference_league",
    "premier_league",
    "bundesliga",
)

DEFAULT_TIMEZONE = "Europe/Vienna"
DEFAULT_MAX_API_FOOTBALL_CALLS = 100
DEFAULT_MAX_SPORTMONKS_CALLS = 100
DEFAULT_MAX_ODDALERTS_CALLS = 100
DEFAULT_PREMATCH_WINDOW_HOURS = 3.0

REPORTS_DIR = Path("reports") / "owner"
ARTIFACTS_DIR = Path("artifacts")
LOGS_DIR = Path("logs")

OWNER_LABEL_STRONG = "STRONG_SIGNAL"
OWNER_LABEL_MEDIUM = "MEDIUM_SIGNAL"
OWNER_LABEL_WEAK = "WEAK_SIGNAL"
OWNER_LABEL_NO_BET = "NO_BET"
OWNER_LABEL_DATA_MISSING = "DATA_MISSING"
