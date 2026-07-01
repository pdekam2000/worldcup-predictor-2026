"""PHASE SAFE-BETS-1 — SQLite DDL."""

from __future__ import annotations

PHASE = "SAFE-BETS-1"

PHASE_SAFE_BETS_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS safe_bet_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_key TEXT NOT NULL UNIQUE,
        scan_batch_id TEXT NOT NULL,
        fixture_id INTEGER NOT NULL,
        match_name TEXT,
        kickoff_utc TEXT,
        market TEXT NOT NULL,
        market_type TEXT,
        selection TEXT NOT NULL,
        odds REAL NOT NULL,
        implied_probability REAL NOT NULL,
        devigged_probability REAL,
        probability_bucket TEXT,
        usefulness_score REAL NOT NULL,
        trap_flag INTEGER NOT NULL DEFAULT 0,
        reason TEXT,
        provider TEXT NOT NULL,
        bookmaker TEXT,
        data_quality REAL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_safe_bets_fixture
    ON safe_bet_candidates(fixture_id, probability_bucket, usefulness_score DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_safe_bets_batch
    ON safe_bet_candidates(scan_batch_id, created_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS safe_bets_scan_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_batch_id TEXT NOT NULL UNIQUE,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,
        hours_window INTEGER,
        fixtures_scanned INTEGER,
        candidates_stored INTEGER,
        traps_flagged INTEGER,
        api_calls INTEGER,
        report_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS safe_bets_api_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_batch_id TEXT,
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
    CREATE INDEX IF NOT EXISTS idx_safe_bets_api_log_batch
    ON safe_bets_api_log(scan_batch_id, created_at DESC)
    """,
)
