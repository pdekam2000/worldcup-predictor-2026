"""DDL for prematch feature snapshot store."""

PREMATCH_FEATURE_DDL = (
    """
    CREATE TABLE IF NOT EXISTS prematch_feature_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_key TEXT NOT NULL UNIQUE,
        fixture_id INTEGER NOT NULL,
        competition_key TEXT NOT NULL,
        tier TEXT,
        provider TEXT NOT NULL,
        provider_fixture_id INTEGER,
        feature_family TEXT NOT NULL,
        feature_name TEXT NOT NULL DEFAULT '',
        feature_version TEXT NOT NULL,
        feature_available_at_utc TEXT NOT NULL,
        fetched_at_utc TEXT NOT NULL,
        prediction_cutoff_utc TEXT NOT NULL,
        kickoff_utc TEXT NOT NULL,
        source_endpoint TEXT,
        source_version TEXT,
        leakage_status TEXT NOT NULL,
        mapping_confidence REAL,
        data_quality TEXT,
        completeness_mask TEXT,
        payload_hash TEXT,
        payload_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_prematch_feature_fixture
    ON prematch_feature_snapshots(fixture_id, feature_family)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_prematch_feature_competition
    ON prematch_feature_snapshots(competition_key, feature_family)
    """,
    """
    CREATE TABLE IF NOT EXISTS prematch_feature_backfill_checkpoint (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        phase TEXT NOT NULL,
        last_fixture_id INTEGER,
        api_calls_used INTEGER NOT NULL DEFAULT 0,
        sportmonks_calls_used INTEGER NOT NULL DEFAULT 0,
        updated_at_utc TEXT NOT NULL
    )
    """,
)
