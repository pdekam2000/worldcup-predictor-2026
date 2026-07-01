"""PHASE ODDALERTS-CSV-PLAYER-REF-1 — DDL for OddAlerts enrichment CSV tables."""

from __future__ import annotations

PHASE = "ODDALERTS-CSV-PLAYER-REF-1"

ODDALERTS_ENRICHMENT_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS oddalerts_player_stats_raw (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_file TEXT NOT NULL,
        row_hash TEXT NOT NULL UNIQUE,
        imported_at TEXT NOT NULL,
        raw_row_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_oa_player_stats_raw_source
    ON oddalerts_player_stats_raw(source_file, imported_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS oddalerts_player_stats_normalized (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        row_hash TEXT NOT NULL UNIQUE,
        player TEXT,
        full_name TEXT,
        nationality TEXT,
        age REAL,
        position TEXT,
        team TEXT,
        fixture_name TEXT,
        fixture_date_text TEXT,
        kickoff_unix INTEGER,
        country TEXT,
        competition_name TEXT,
        competition_type TEXT,
        apps REAL,
        starts REAL,
        mins REAL,
        goals REAL,
        goals_avg REAL,
        assists REAL,
        shots REAL,
        shots_ot REAL,
        key_passes REAL,
        passes REAL,
        pass_accuracy REAL,
        tackles REAL,
        interceptions REAL,
        saves REAL,
        clean_sheets REAL,
        yellow_cards REAL,
        red_cards REAL,
        pens_scored REAL,
        rating REAL,
        is_captain INTEGER,
        is_injured INTEGER,
        source_file TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_oa_player_stats_norm_fixture
    ON oddalerts_player_stats_normalized(fixture_name, team)
    """,
    """
    CREATE TABLE IF NOT EXISTS oddalerts_referee_cards_raw (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_file TEXT NOT NULL,
        row_hash TEXT NOT NULL UNIQUE,
        imported_at TEXT NOT NULL,
        raw_row_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_oa_ref_cards_raw_source
    ON oddalerts_referee_cards_raw(source_file, imported_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS oddalerts_referee_cards_normalized (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        row_hash TEXT NOT NULL UNIQUE,
        referee_name TEXT,
        fixture_name TEXT,
        fixture_date_text TEXT,
        country TEXT,
        competition_type TEXT,
        label TEXT,
        recorded TEXT,
        yellow_cards REAL,
        red_cards REAL,
        yellow_cards_avg REAL,
        red_cards_avg REAL,
        cards_1h REAL,
        cards_2h REAL,
        cards_1h_avg REAL,
        cards_2h_avg REAL,
        both_teams_booked_per REAL,
        home_cards_avg REAL,
        away_cards_avg REAL,
        o05_yellow_cards_per REAL,
        o15_yellow_cards_per REAL,
        o25_yellow_cards_per REAL,
        o35_yellow_cards_per REAL,
        o45_yellow_cards_per REAL,
        o55_yellow_cards_per REAL,
        source_file TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_oa_ref_cards_norm_fixture
    ON oddalerts_referee_cards_normalized(fixture_name)
    """,
    """
    CREATE TABLE IF NOT EXISTS oddalerts_enrichment_fixture_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        enrichment_type TEXT NOT NULL,
        row_hash TEXT NOT NULL,
        fixture_id INTEGER,
        fixture_name_source TEXT,
        match_status TEXT NOT NULL,
        confidence REAL,
        rejection_reason TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(enrichment_type, row_hash)
    )
    """,
)


def ensure_oddalerts_enrichment_tables(conn) -> None:
    for ddl in ODDALERTS_ENRICHMENT_DDL:
        conn.execute(ddl)
