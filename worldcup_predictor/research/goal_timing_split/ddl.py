"""PHASE GT-1 — Goal timing split predictions DDL."""

from __future__ import annotations

PHASE = "GT-1"

PHASE_GOAL_TIMING_SPLIT_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS goal_timing_split_predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prediction_key TEXT NOT NULL UNIQUE,
        fixture_id INTEGER NOT NULL,
        match_name TEXT,
        kickoff_utc TEXT,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        p_home_0_30 REAL,
        p_away_0_30 REAL,
        p_home_31_plus REAL,
        p_away_31_plus REAL,
        p_no_goal REAL,
        recommended_side TEXT NOT NULL,
        recommended_window TEXT NOT NULL,
        confidence_tier TEXT NOT NULL,
        data_quality_score REAL,
        raw_features_json TEXT,
        created_at TEXT NOT NULL,
        model_version TEXT NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_gt_split_fixture_model
    ON goal_timing_split_predictions(fixture_id, model_version)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gt_split_created
    ON goal_timing_split_predictions(created_at DESC)
    """,
)
