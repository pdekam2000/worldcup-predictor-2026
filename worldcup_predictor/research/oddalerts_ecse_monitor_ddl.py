"""PHASE ECSE-ODDALERTS-5 — limited shadow monitor DDL."""

from __future__ import annotations

PHASE = "ECSE-ODDALERTS-5"

ECSE_ODDALERTS_MONITOR_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS ecse_oddalerts_shadow_monitor (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        odds_snapshot_id INTEGER NOT NULL,
        home_team TEXT,
        away_team TEXT,
        competition TEXT,
        kickoff_utc TEXT,
        source_provider TEXT NOT NULL,
        source_detail TEXT NOT NULL,
        lambda_home REAL NOT NULL,
        lambda_away REAL NOT NULL,
        top_1_score TEXT NOT NULL,
        top_3_scores_json TEXT NOT NULL,
        top_5_scores_json TEXT NOT NULL,
        top_10_scores_json TEXT NOT NULL,
        segment_model_version TEXT NOT NULL,
        segment_score_v2 REAL NOT NULL,
        segment_badge_v2 TEXT NOT NULL,
        expected_top3_rate REAL,
        expected_top5_rate REAL,
        top5_value_signal INTEGER NOT NULL DEFAULT 0,
        promotion_eligibility_v2 TEXT NOT NULL,
        reasons_json TEXT,
        cautions_json TEXT,
        input_market_probabilities_json TEXT,
        source_trace_json TEXT,
        monitor_run_id TEXT NOT NULL,
        record_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        evaluated_at TEXT,
        final_score TEXT,
        top1_hit INTEGER,
        top3_hit INTEGER,
        top5_hit INTEGER,
        top10_hit INTEGER,
        UNIQUE(record_hash),
        UNIQUE(fixture_id, odds_snapshot_id, segment_model_version)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ecse_oa_monitor_run
    ON ecse_oddalerts_shadow_monitor(monitor_run_id, kickoff_utc)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ecse_oa_monitor_fixture
    ON ecse_oddalerts_shadow_monitor(fixture_id)
    """,
)
