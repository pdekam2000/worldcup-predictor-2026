"""SQLite schema for football intelligence database."""

from __future__ import annotations

SCHEMA_VERSION = 1
DEFAULT_DB_PATH = "data/football_intelligence.db"

DDL_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS competitions (
        key TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        league_id INTEGER,
        season INTEGER,
        competition_type TEXT NOT NULL DEFAULT 'tournament',
        supports_groups INTEGER NOT NULL DEFAULT 0,
        supports_table INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_team_id INTEGER,
        name TEXT NOT NULL,
        competition_key TEXT NOT NULL,
        UNIQUE(api_team_id, competition_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fixtures (
        fixture_id INTEGER PRIMARY KEY,
        competition_key TEXT NOT NULL,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        home_team_id INTEGER,
        away_team_id INTEGER,
        kickoff_utc TEXT,
        status TEXT NOT NULL DEFAULT 'NS',
        round_name TEXT,
        group_name TEXT,
        venue TEXT,
        city TEXT,
        source TEXT NOT NULL DEFAULT 'live',
        is_placeholder INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (competition_key) REFERENCES competitions(key)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_fixtures_competition_kickoff
    ON fixtures(competition_key, kickoff_utc)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_fixtures_status
    ON fixtures(status)
    """,
    """
    CREATE TABLE IF NOT EXISTS fixture_results (
        fixture_id INTEGER PRIMARY KEY,
        competition_key TEXT NOT NULL,
        final_score TEXT,
        halftime_score TEXT,
        home_goals INTEGER,
        away_goals INTEGER,
        winner TEXT,
        over_under_2_5 TEXT,
        total_goals INTEGER,
        finished_at TEXT,
        source TEXT NOT NULL DEFAULT 'live',
        FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS predictions (
        prediction_id TEXT PRIMARY KEY,
        fixture_id INTEGER NOT NULL,
        competition_key TEXT NOT NULL,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        prediction_version TEXT NOT NULL DEFAULT 'manual',
        created_at TEXT NOT NULL,
        data_quality REAL NOT NULL DEFAULT 0,
        prediction_quality REAL NOT NULL DEFAULT 0,
        confidence REAL NOT NULL DEFAULT 0,
        no_bet_flag INTEGER NOT NULL DEFAULT 0,
        selected_by_engine INTEGER NOT NULL DEFAULT 0,
        reason_selected TEXT,
        source TEXT NOT NULL DEFAULT 'live',
        lineups_available INTEGER NOT NULL DEFAULT 0,
        is_preliminary INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_predictions_competition
    ON predictions(competition_key, created_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS prediction_markets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prediction_id TEXT NOT NULL,
        market TEXT NOT NULL,
        predicted_value TEXT NOT NULL,
        UNIQUE(prediction_id, market),
        FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS verification_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        prediction_id TEXT NOT NULL,
        competition_key TEXT,
        market TEXT NOT NULL,
        predicted TEXT NOT NULL,
        actual TEXT NOT NULL,
        result TEXT NOT NULL,
        color TEXT NOT NULL,
        verified_at TEXT NOT NULL,
        UNIQUE(fixture_id, prediction_id, market)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS team_form_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        team_name TEXT NOT NULL,
        competition_key TEXT NOT NULL,
        snapshot_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS odds_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        competition_key TEXT NOT NULL,
        snapshot_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS xg_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        competition_key TEXT NOT NULL,
        snapshot_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_stats_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        competition_key TEXT NOT NULL,
        snapshot_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        competition_key TEXT NOT NULL,
        agent_name TEXT NOT NULL,
        signal_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_coach_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        competition_key TEXT,
        generated_at TEXT NOT NULL,
        report_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS selection_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        competition_key TEXT NOT NULL,
        selection_level TEXT NOT NULL,
        total_score REAL NOT NULL,
        scores_json TEXT NOT NULL,
        reason TEXT NOT NULL,
        expected_improvement TEXT,
        decided_at TEXT NOT NULL,
        UNIQUE(fixture_id, decided_at)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_records_v2 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_id TEXT NOT NULL UNIQUE,
        fixture_id INTEGER NOT NULL,
        prediction_id TEXT NOT NULL,
        competition_key TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        verified_at TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_learning_records_v2_fixture
    ON learning_records_v2(fixture_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_learning_records_v2_competition
    ON learning_records_v2(competition_key, created_at)
    """,
)
