"""Phase 52A — Survival analysis configuration (shadow mode only)."""

from __future__ import annotations

from pathlib import Path

SURVIVAL_MODEL_VERSION = "egie_survival_v0.1_phase52a_shadow"

# Minute checkpoints for survival curve reporting
SURVIVAL_MINUTE_CHECKPOINTS: tuple[int, ...] = (15, 30, 45, 60, 75, 90)

# Bucket bounds (inclusive) aligned with GOAL_TIMING_MINUTE_RANGES
RANGE_BUCKET_BOUNDS: dict[str, tuple[int, int]] = {
    "0-15": (1, 15),
    "16-30": (16, 30),
    "31-45+": (31, 45),
    "46-60": (46, 60),
    "61-75": (61, 75),
    "76-90+": (76, 90),
}

# Blend weights for match-level range probabilities
LEAGUE_RANGE_WEIGHT = 0.40
HOME_PROFILE_RANGE_WEIGHT = 0.30
AWAY_PROFILE_RANGE_WEIGHT = 0.30

# First-goal team abstention (unchanged from baseline — shadow pick only)
TEAM_ABSTAIN_RATE_GAP = 0.04

# Phase 52A success criteria (vs Phase 51H baseline on same cohort)
SUCCESS_CRITERIA = {
    "goal_range_winrate_min": 0.35,
    "goal_minute_soft_winrate_min": 0.40,
    "first_goal_team_winrate_min": 0.508,
}

BASELINE_REFERENCE = {
    "first_goal_team": 0.5076,
    "goal_range": 0.2779,
    "goal_minute_exact": 0.0335,
    "goal_minute_soft": 0.3381,
}

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "egie" / "survival"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

SURVIVAL_DATASET_PATH = DATA_DIR / "survival_dataset.parquet"
TEAM_PROFILES_PATH = DATA_DIR / "team_timing_profiles.json"
SHADOW_PREDICTIONS_PATH = DATA_DIR / "survival_shadow_predictions.jsonl"
