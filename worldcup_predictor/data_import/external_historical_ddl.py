"""DDL for external historical CSV ZIP staging (HISTORICAL-CSV-INGEST-1)."""

from __future__ import annotations

EXTERNAL_HISTORICAL_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS external_historical_csv_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_zip TEXT NOT NULL,
        source_file TEXT NOT NULL,
        file_hash TEXT NOT NULL UNIQUE,
        rows_count INTEGER NOT NULL DEFAULT 0,
        country_name TEXT,
        league_code TEXT,
        min_event_date TEXT,
        max_event_date TEXT,
        status TEXT NOT NULL DEFAULT 'staged',
        imported_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_external_historical_csv_files_source
    ON external_historical_csv_files(source_zip, source_file)
    """,
    """
    CREATE TABLE IF NOT EXISTS external_historical_csv_raw_rows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_hash TEXT NOT NULL,
        row_hash TEXT NOT NULL UNIQUE,
        source_file TEXT NOT NULL,
        row_number INTEGER NOT NULL,
        raw_row_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_external_historical_raw_file_hash
    ON external_historical_csv_raw_rows(file_hash)
    """,
    """
    CREATE TABLE IF NOT EXISTS external_match_history_staging (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        row_hash TEXT NOT NULL UNIQUE,
        source_file TEXT NOT NULL,
        sport TEXT,
        league TEXT,
        country_name TEXT,
        home_team TEXT,
        away_team TEXT,
        round TEXT,
        status TEXT,
        event_date TEXT,
        event_hour TEXT,
        kickoff_utc TEXT,
        home_ht_goals INTEGER,
        away_ht_goals INTEGER,
        home_ft_goals INTEGER,
        away_ft_goals INTEGER,
        home_xg REAL,
        away_xg REAL,
        home_penalties INTEGER,
        away_penalties INTEGER,
        home_corners INTEGER,
        away_corners INTEGER,
        raw_row_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_external_match_history_event
    ON external_match_history_staging(event_date, home_team, away_team)
    """,
    """
    CREATE TABLE IF NOT EXISTS external_match_odds_staging (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        row_hash TEXT NOT NULL UNIQUE,
        source_file TEXT NOT NULL,
        league TEXT,
        country_name TEXT,
        home_team TEXT,
        away_team TEXT,
        event_date TEXT,
        event_hour TEXT,
        market TEXT NOT NULL,
        outcome TEXT NOT NULL,
        odds REAL,
        implied_probability REAL,
        period TEXT NOT NULL,
        raw_row_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_external_match_odds_event
    ON external_match_odds_staging(event_date, home_team, away_team, market)
    """,
)


def ensure_external_historical_tables(conn) -> None:
    for ddl in EXTERNAL_HISTORICAL_DDL:
        conn.execute(ddl)
