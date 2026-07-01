"""PHASE ECSE-ODDALERTS-2 — shadow ECSE predictions from OddAlerts CSV snapshots."""

from __future__ import annotations

PHASE = "ECSE-ODDALERTS-2"

ECSE_ODDALERTS_SHADOW_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS ecse_oddalerts_shadow_predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        home_team TEXT,
        away_team TEXT,
        competition TEXT,
        kickoff_utc TEXT,
        odds_snapshot_id INTEGER NOT NULL,
        source_provider TEXT NOT NULL,
        source_detail TEXT NOT NULL,
        policy_version TEXT,
        promotion_action TEXT,
        lambda_home REAL NOT NULL,
        lambda_away REAL NOT NULL,
        top_1_score TEXT NOT NULL,
        top_3_scores_json TEXT NOT NULL,
        top_5_scores_json TEXT NOT NULL,
        top_10_scores_json TEXT NOT NULL,
        input_market_probabilities_json TEXT,
        warning_flags_json TEXT,
        normalization_notes_json TEXT,
        source_bookmakers_json TEXT,
        source_row_hashes_json TEXT,
        source_files_json TEXT,
        crosswalk_confidence TEXT,
        confidence_score REAL,
        confidence_tier TEXT,
        data_quality_score REAL,
        generated_at TEXT NOT NULL,
        shadow_run_id TEXT NOT NULL,
        record_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(record_hash),
        UNIQUE(fixture_id, odds_snapshot_id, shadow_run_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ecse_oa_shadow_run
    ON ecse_oddalerts_shadow_predictions(shadow_run_id, fixture_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ecse_oa_shadow_fixture
    ON ecse_oddalerts_shadow_predictions(fixture_id)
    """,
)
