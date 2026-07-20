"""ECSE timing experiment — research-only constants."""

from __future__ import annotations

from pathlib import Path

PHASE = "ECSE_TIMING_EXPERIMENT_V1"
TZ_NAME = "Europe/Vienna"
DB_RELATIVE = Path("data/research/ecse_timing_experiment.db")
ARTIFACT_ROOT = Path("artifacts/research/ecse_timing_experiment")
REPORT_ROOT = Path("reports/research")
DOCS_PATH = Path("docs/research/ecse_timing_experiment.md")

SNAPSHOT_CLASSES = ("EARLY", "MID", "LATE")

# Target hours-to-kickoff windows (inclusive bounds)
EARLY_HOURS = (18.0, 30.0)
MID_HOURS = (6.0, 12.0)
LATE_HOURS = (1.0, 3.0)

WINDOW_LABELS = {
    "EARLY": ("EARLY_IN_WINDOW", "EARLY_TOO_EARLY", "EARLY_TOO_LATE"),
    "MID": ("MID_IN_WINDOW", "MID_TOO_EARLY", "MID_TOO_LATE"),
    "LATE": ("LATE_IN_WINDOW", "LATE_TOO_EARLY", "LATE_TOO_LATE"),
}

BLOCKED_STATUSES = frozenset(
    {
        "BLOCKED_STALE_ODDS",
        "BLOCKED_INCOMPLETE_ODDS",
        "BLOCKED_FIXTURE_STARTED",
        "BLOCKED_UNSUPPORTED_FIXTURE",
        "BLOCKED_PROVIDER_FAILURE",
        "BLOCKED_MODEL_FAILURE",
        "BLOCKED_RESTORE_FAILURE",
        "BLOCKED_ALREADY_CAPTURED",  # not a block — reserved; use IDEMPOTENT
        "BLOCKED_DRY_RUN",
    }
)

STARTED = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "PEN"})
FINISHED = frozenset({"FT", "AET", "PEN"})
UNRESOLVED = frozenset({"CANC", "ABD", "PST", "SUSP", "INT", "AWD", "WO", "NS", "TBD", "SCHEDULED", "TIMED", ""})
PREMATCH = frozenset({"NS", "TBD", "SCHEDULED", "TIMED", ""})
FRIENDLY_KEYS = frozenset(
    {
        "friendlies",
        "friendly",
        "club_friendlies",
        "international_friendlies",
        "league_667",
    }
)

STABILITY_LABELS = (
    "FULLY_STABLE",
    "SET_STABLE_RANK_REORDERED",
    "BOUNDARY_CHANGED",
    "TOP1_CHANGED",
    "WDE_CHANGED",
    "MAJOR_MODEL_MOVEMENT",
)

EVENT_LABELS = (
    "LATE_REFRESH_IMPROVED_TOP5",
    "LATE_REFRESH_DEGRADED_TOP5",
    "MID_REFRESH_IMPROVED_TOP5",
    "MID_REFRESH_DEGRADED_TOP5",
    "CORRECT_SCORE_STABLE_ALL_SNAPSHOTS",
    "CORRECT_SCORE_NEVER_IN_TOP5",
    "BOUNDARY_SCORE_INSTABILITY",
)

INTERPRETATION_BANDS = (
    (0, 29, "descriptive_only"),
    (30, 79, "preliminary"),
    (80, 99, "meaningful_provisional"),
    (100, 10_000_000, "stronger_research_eligible"),
)
