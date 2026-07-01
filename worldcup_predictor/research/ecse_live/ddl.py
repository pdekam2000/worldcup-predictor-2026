"""PHASE ECSE-LIVE-1 — SQLite DDL for ECSE live snapshots and evaluations."""

from __future__ import annotations

PHASE = "ECSE-LIVE-1"

PHASE_ECSE_LIVE_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS ecse_prediction_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_key TEXT NOT NULL UNIQUE,
        fixture_id INTEGER NOT NULL UNIQUE,
        registry_fixture_id INTEGER,
        competition_key TEXT,
        home_team TEXT,
        away_team TEXT,
        kickoff_utc TEXT,
        generated_at TEXT NOT NULL,
        model_version TEXT NOT NULL,
        lambda_home REAL NOT NULL,
        lambda_away REAL NOT NULL,
        top_10_scorelines_json TEXT NOT NULL,
        top_1_score TEXT NOT NULL,
        top_3_scores_json TEXT NOT NULL,
        top_5_scores_json TEXT NOT NULL,
        confidence_score REAL NOT NULL,
        data_quality_score REAL NOT NULL,
        raw_features_json TEXT,
        prediction_source TEXT NOT NULL DEFAULT 'live_odds',
        is_frozen INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ecse_snap_kickoff
    ON ecse_prediction_snapshots(kickoff_utc)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ecse_snap_registry
    ON ecse_prediction_snapshots(registry_fixture_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS ecse_prediction_evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_id INTEGER NOT NULL UNIQUE,
        fixture_id INTEGER NOT NULL,
        final_score TEXT,
        top1_correct INTEGER NOT NULL DEFAULT 0,
        top3_correct INTEGER NOT NULL DEFAULT 0,
        top5_correct INTEGER NOT NULL DEFAULT 0,
        top10_correct INTEGER NOT NULL DEFAULT 0,
        rank_of_actual_score INTEGER,
        actual_home_goals INTEGER,
        actual_away_goals INTEGER,
        status TEXT NOT NULL DEFAULT 'evaluated',
        evaluated_at TEXT NOT NULL,
        FOREIGN KEY(snapshot_id) REFERENCES ecse_prediction_snapshots(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ecse_eval_fixture
    ON ecse_prediction_evaluations(fixture_id, evaluated_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS ecse_live_cycle_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,
        report_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ecse_live_api_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phase TEXT NOT NULL DEFAULT 'ECSE-LIVE-1',
        provider TEXT NOT NULL,
        endpoint TEXT NOT NULL,
        entity_key TEXT,
        action TEXT NOT NULL,
        status TEXT NOT NULL,
        details_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ecse_live_api_log_provider
    ON ecse_live_api_log(provider, created_at DESC)
    """,
)
