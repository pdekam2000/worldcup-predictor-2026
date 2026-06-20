"""Apply incremental schema migrations — idempotent, safe on existing databases."""

from __future__ import annotations

import sqlite3

from worldcup_predictor.database.schema import PHASE40_DDL, SCHEMA_VERSION

# Phase 39 tables/indexes (CREATE IF NOT EXISTS — never drops data)
PHASE39_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS fixture_enrichment (
        fixture_id INTEGER PRIMARY KEY,
        competition_key TEXT NOT NULL,
        league_id INTEGER,
        season INTEGER,
        events_json TEXT,
        lineups_json TEXT,
        statistics_json TEXT,
        players_json TEXT,
        odds_json TEXT,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS league_import_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        competition_key TEXT NOT NULL,
        league_id INTEGER NOT NULL,
        season INTEGER NOT NULL,
        fixtures_imported INTEGER NOT NULL DEFAULT 0,
        fixtures_skipped INTEGER NOT NULL DEFAULT 0,
        enrichment_errors INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        message TEXT,
        started_at TEXT NOT NULL,
        finished_at TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_league_import_runs_comp_season
    ON league_import_runs(competition_key, season)
    """,
)

PHASE39_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("fixtures", "league_id", "INTEGER"),
    ("fixtures", "season", "INTEGER"),
    ("learning_records_v2", "learning_profile_key", "TEXT"),
)

PHASE41_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS sportmonks_fixture_enrichment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id_api_football INTEGER,
        sportmonks_fixture_id INTEGER NOT NULL UNIQUE,
        league_id INTEGER NOT NULL,
        season_id INTEGER NOT NULL,
        endpoint TEXT NOT NULL,
        include_params TEXT NOT NULL,
        raw_json TEXT NOT NULL,
        fetched_at_utc TEXT NOT NULL,
        expires_at_utc TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ok'
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sportmonks_fixture_enrichment_expires
    ON sportmonks_fixture_enrichment(expires_at_utc)
    """,
)

# Phase 28B — premium include access flags (non-destructive ALTER)
PHASE42B_SPORTMONKS_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("sportmonks_fixture_enrichment", "base_enrichment_available", "INTEGER NOT NULL DEFAULT 0"),
    ("sportmonks_fixture_enrichment", "premium_odds_available", "INTEGER NOT NULL DEFAULT 0"),
    ("sportmonks_fixture_enrichment", "premium_predictions_available", "INTEGER NOT NULL DEFAULT 0"),
    ("sportmonks_fixture_enrichment", "premium_xg_available", "INTEGER NOT NULL DEFAULT 0"),
    ("sportmonks_fixture_enrichment", "premium_odds_access_denied", "INTEGER NOT NULL DEFAULT 0"),
    ("sportmonks_fixture_enrichment", "premium_predictions_access_denied", "INTEGER NOT NULL DEFAULT 0"),
    ("sportmonks_fixture_enrichment", "premium_xg_access_denied", "INTEGER NOT NULL DEFAULT 0"),
)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    typedef: str,
) -> bool:
    if column in _column_names(conn, table):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")
    return True


def ensure_schema_compat(conn: sqlite3.Connection) -> None:
    """Ensure Phase 39 columns/tables exist — always safe to call."""
    for ddl in PHASE39_DDL:
        conn.execute(ddl)

    for table, column, typedef in PHASE39_COLUMNS:
        if _table_exists(conn, table):
            _add_column_if_missing(conn, table, column, typedef)

    for ddl in PHASE40_DDL:
        conn.execute(ddl)

    for ddl in PHASE41_DDL:
        conn.execute(ddl)

    for table, column, typedef in PHASE42B_SPORTMONKS_COLUMNS:
        if _table_exists(conn, table):
            _add_column_if_missing(conn, table, column, typedef)

    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )
    conn.commit()


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Legacy entry point — always runs idempotent schema compatibility checks."""
    ensure_schema_compat(conn)
