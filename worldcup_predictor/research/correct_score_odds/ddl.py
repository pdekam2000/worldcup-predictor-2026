"""Additive DDL for structured Correct Score odds lines (append-only)."""

from __future__ import annotations

import sqlite3

PHASE_CS_ODDS_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS correct_score_odds_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        provider_fixture_id TEXT,
        bookmaker_id TEXT,
        bookmaker_name TEXT NOT NULL,
        market TEXT NOT NULL,
        selection TEXT NOT NULL,
        home_goals INTEGER,
        away_goals INTEGER,
        decimal_odds REAL NOT NULL,
        raw_odds_format TEXT NOT NULL DEFAULT 'decimal',
        fetched_at_utc TEXT NOT NULL,
        valid_from_utc TEXT,
        kickoff_utc TEXT,
        prematch_status TEXT NOT NULL,
        settlement_scope TEXT NOT NULL DEFAULT '90_MINUTES',
        provider TEXT NOT NULL,
        source_hash TEXT NOT NULL,
        payload_reference TEXT,
        snapshot_id INTEGER,
        is_complete_market INTEGER NOT NULL DEFAULT 0,
        is_fresh INTEGER NOT NULL DEFAULT 1,
        odds_age_seconds REAL,
        currency TEXT,
        minimum_stake REAL,
        maximum_stake REAL,
        market_status TEXT NOT NULL DEFAULT 'open',
        ingestion_run_id TEXT NOT NULL,
        odds_kind TEXT NOT NULL DEFAULT 'api_extracted',
        created_at_utc TEXT NOT NULL,
        UNIQUE (
            fixture_id, provider, bookmaker_name, market, selection,
            fetched_at_utc, source_hash
        )
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cs_odds_fixture_fetched
    ON correct_score_odds_lines(fixture_id, fetched_at_utc)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cs_odds_run
    ON correct_score_odds_lines(ingestion_run_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS correct_score_odds_ingestion_runs (
        ingestion_run_id TEXT PRIMARY KEY,
        started_at_utc TEXT NOT NULL,
        finished_at_utc TEXT,
        mode TEXT NOT NULL,
        fixtures_scanned INTEGER NOT NULL DEFAULT 0,
        lines_inserted INTEGER NOT NULL DEFAULT 0,
        lines_rejected INTEGER NOT NULL DEFAULT 0,
        lines_deduped INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        notes_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS correct_score_odds_manual_imports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        bookmaker_name TEXT NOT NULL,
        capture_timestamp_utc TEXT NOT NULL,
        settlement_scope TEXT NOT NULL DEFAULT '90_MINUTES',
        owner_confirmed INTEGER NOT NULL DEFAULT 0,
        confirmed_at_utc TEXT,
        raw_image_path TEXT,
        rows_json TEXT NOT NULL,
        odds_kind TEXT NOT NULL DEFAULT 'manual_owner_confirmed',
        created_at_utc TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS correct_score_forward_collection_plan (
        fixture_id INTEGER NOT NULL,
        kickoff_utc TEXT NOT NULL,
        window_label TEXT NOT NULL,
        target_collect_utc TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'planned',
        collected_at_utc TEXT,
        ingestion_run_id TEXT,
        PRIMARY KEY (fixture_id, window_label)
    )
    """,
)


def ensure_correct_score_odds_schema(conn: sqlite3.Connection) -> None:
    for ddl in PHASE_CS_ODDS_DDL:
        conn.execute(ddl)
    conn.commit()
