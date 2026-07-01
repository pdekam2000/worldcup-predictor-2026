"""DDL for normalized OddAlerts probability market rows."""

ODDALERTS_PROBABILITY_MARKET_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS oddalerts_probability_market_rows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        row_hash TEXT NOT NULL UNIQUE,
        source_file TEXT NOT NULL,
        source_file_hash TEXT NOT NULL,
        export_email_date TEXT,
        export_market TEXT,
        export_outcome TEXT,
        normalized_market_key TEXT,
        market_family TEXT,
        threshold_value REAL,
        side TEXT,
        outcome_type TEXT,
        bookmaker TEXT NOT NULL,
        bookmaker_slug TEXT,
        probability_min REAL,
        probability_max REAL,
        export_date_start TEXT,
        export_date_end TEXT,
        fixture_name TEXT,
        fixture_date TEXT,
        kickoff_time TEXT,
        competition_name TEXT,
        country TEXT,
        home_team_normalized TEXT,
        away_team_normalized TEXT,
        internal_fixture_id INTEGER,
        fixture_match_status TEXT,
        fixture_match_confidence REAL,
        model_probability REAL,
        opening_odds REAL,
        closing_odds REAL,
        peak_odds REAL,
        raw_row_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_oapm_normalized_market
    ON oddalerts_probability_market_rows(normalized_market_key, bookmaker)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_oapm_fixture
    ON oddalerts_probability_market_rows(internal_fixture_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_oapm_source_file
    ON oddalerts_probability_market_rows(source_file)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_oapm_fixture_name
    ON oddalerts_probability_market_rows(fixture_name, kickoff_time)
    """,
)


def ensure_oddalerts_probability_market_tables(conn) -> None:
    for ddl in ODDALERTS_PROBABILITY_MARKET_DDL:
        conn.execute(ddl)
