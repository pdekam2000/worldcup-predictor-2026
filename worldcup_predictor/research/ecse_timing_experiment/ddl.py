"""Additive DDL for ECSE timing experiment (research-only DB)."""

from __future__ import annotations

import sqlite3

PHASE_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS timing_experiments (
        experiment_id TEXT PRIMARY KEY,
        experiment_date TEXT NOT NULL,
        timezone TEXT NOT NULL,
        scope TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        status TEXT NOT NULL,
        git_sha TEXT,
        meta_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS timing_experiment_fixtures (
        experiment_id TEXT NOT NULL,
        fixture_id INTEGER NOT NULL,
        home_team TEXT,
        away_team TEXT,
        league TEXT,
        country TEXT,
        competition_key TEXT,
        kickoff_utc TEXT,
        kickoff_vienna TEXT,
        tier TEXT,
        prediction_scope TEXT,
        discovery_status TEXT NOT NULL,
        exclusion_reason TEXT,
        provider TEXT,
        bookmaker_count INTEGER,
        latest_odds_timestamp TEXT,
        meta_json TEXT,
        PRIMARY KEY (experiment_id, fixture_id),
        FOREIGN KEY (experiment_id) REFERENCES timing_experiments(experiment_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS timing_prediction_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        experiment_id TEXT NOT NULL,
        fixture_id INTEGER NOT NULL,
        snapshot_class TEXT NOT NULL,
        window_classification TEXT,
        hours_to_kickoff REAL,
        captured_at_utc TEXT NOT NULL,
        captured_at_vienna TEXT,
        status TEXT NOT NULL,
        block_reason TEXT,
        payload_json TEXT NOT NULL,
        research_output_hash TEXT NOT NULL,
        odds_content_hash TEXT,
        model_config_hash TEXT,
        freeze_id TEXT,
        freeze_hash TEXT,
        freeze_unchanged INTEGER,
        freeze_capture INTEGER NOT NULL DEFAULT 0,
        wsp_restored INTEGER,
        temporary_run_audit_id TEXT,
        UNIQUE (experiment_id, fixture_id, snapshot_class),
        FOREIGN KEY (experiment_id) REFERENCES timing_experiments(experiment_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_timing_snaps_exp_class
    ON timing_prediction_snapshots(experiment_id, snapshot_class, status)
    """,
    """
    CREATE TABLE IF NOT EXISTS timing_snapshot_comparisons (
        comparison_id TEXT PRIMARY KEY,
        experiment_id TEXT NOT NULL,
        fixture_id INTEGER NOT NULL,
        from_class TEXT NOT NULL,
        to_class TEXT NOT NULL,
        compared_at_utc TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        primary_stability_label TEXT,
        labels_json TEXT,
        UNIQUE (experiment_id, fixture_id, from_class, to_class)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS timing_result_evaluations (
        evaluation_id TEXT PRIMARY KEY,
        experiment_id TEXT NOT NULL,
        fixture_id INTEGER NOT NULL,
        snapshot_class TEXT NOT NULL,
        evaluated_at_utc TEXT NOT NULL,
        result_status TEXT NOT NULL,
        actual_score TEXT,
        payload_json TEXT NOT NULL,
        event_labels_json TEXT,
        UNIQUE (experiment_id, fixture_id, snapshot_class)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS timing_stable_union_predictions (
        union_id TEXT PRIMARY KEY,
        experiment_id TEXT NOT NULL,
        fixture_id INTEGER NOT NULL,
        built_at_utc TEXT NOT NULL,
        scores_json TEXT NOT NULL,
        research_only INTEGER NOT NULL DEFAULT 1,
        canonical INTEGER NOT NULL DEFAULT 0,
        final_decision_authority INTEGER NOT NULL DEFAULT 0,
        payload_json TEXT NOT NULL,
        UNIQUE (experiment_id, fixture_id)
    )
    """,
)


def ensure_timing_schema(conn: sqlite3.Connection) -> None:
    for ddl in PHASE_DDL:
        conn.execute(ddl)
    conn.commit()
