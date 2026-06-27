"""Phase A23 — SQLite DDL (append-only lifecycle tables)."""

PHASE_A23_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS prediction_lifecycle_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_key TEXT NOT NULL UNIQUE,
        fixture_id INTEGER NOT NULL,
        competition_key TEXT,
        season INTEGER,
        home_team TEXT,
        away_team TEXT,
        kickoff_utc TEXT,
        lifecycle_state TEXT NOT NULL DEFAULT 'generated',
        prediction_at TEXT NOT NULL,
        prediction_version TEXT,
        prediction_source TEXT NOT NULL DEFAULT 'production',
        model_version TEXT,
        engine TEXT,
        snapshot_id TEXT,
        confidence REAL,
        bet_quality_score REAL,
        tier TEXT,
        best_pick TEXT,
        best_value TEXT,
        payload_json TEXT NOT NULL,
        publication_overlay_json TEXT,
        predops_snapshot_json TEXT,
        egie_snapshot_json TEXT,
        paper_betting_flag INTEGER NOT NULL DEFAULT 0,
        combo_recommended_flag INTEGER NOT NULL DEFAULT 0,
        owner_notes TEXT,
        audit_json TEXT,
        shadow_fixture_ref INTEGER,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_plc_records_fixture
    ON prediction_lifecycle_records(fixture_id, prediction_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_plc_records_competition
    ON prediction_lifecycle_records(competition_key, kickoff_utc DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS prediction_lifecycle_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        record_id INTEGER,
        event_at TEXT NOT NULL,
        event_type TEXT NOT NULL,
        lifecycle_state TEXT NOT NULL,
        summary TEXT,
        pick_snapshot TEXT,
        meta_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(record_id) REFERENCES prediction_lifecycle_records(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_plc_events_fixture
    ON prediction_lifecycle_events(fixture_id, event_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS prediction_fixture_results (
        fixture_id INTEGER PRIMARY KEY,
        competition_key TEXT,
        ft_score TEXT,
        ht_score TEXT,
        winner TEXT,
        btts_result TEXT,
        over_under_result TEXT,
        correct_score_result TEXT,
        goal_timing_result TEXT,
        first_goal_team_result TEXT,
        goalscorer_results_json TEXT,
        markets_json TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prediction_market_evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        eval_key TEXT NOT NULL UNIQUE,
        record_id INTEGER NOT NULL,
        fixture_id INTEGER NOT NULL,
        market_id TEXT NOT NULL,
        prediction TEXT,
        actual TEXT,
        result TEXT NOT NULL DEFAULT 'pending',
        color TEXT NOT NULL DEFAULT 'yellow',
        confidence REAL,
        bet_quality_score REAL,
        odds REAL,
        evaluated_at TEXT NOT NULL,
        FOREIGN KEY(record_id) REFERENCES prediction_lifecycle_records(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_plc_market_eval_fixture
    ON prediction_market_evaluations(fixture_id, market_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS prediction_market_accuracy_rollup (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_id TEXT NOT NULL,
        window_key TEXT NOT NULL,
        predictions INTEGER NOT NULL DEFAULT 0,
        correct INTEGER NOT NULL DEFAULT 0,
        wrong INTEGER NOT NULL DEFAULT 0,
        pending INTEGER NOT NULL DEFAULT 0,
        push_count INTEGER NOT NULL DEFAULT 0,
        void_count INTEGER NOT NULL DEFAULT 0,
        accuracy REAL,
        roi REAL,
        avg_confidence REAL,
        avg_bet_quality REAL,
        avg_odds REAL,
        updated_at TEXT NOT NULL,
        UNIQUE(market_id, window_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prediction_model_registry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_id INTEGER NOT NULL,
        fixture_id INTEGER NOT NULL,
        model_role TEXT NOT NULL,
        model_version TEXT,
        publication_version TEXT,
        promotion_version TEXT,
        engine TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(record_id) REFERENCES prediction_lifecycle_records(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_plc_model_fixture
    ON prediction_model_registry(fixture_id, model_role)
    """,
    """
    CREATE TABLE IF NOT EXISTS prediction_best_value_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_id INTEGER NOT NULL,
        fixture_id INTEGER NOT NULL,
        pick_type TEXT NOT NULL,
        pick_value TEXT,
        reason TEXT,
        quality_score REAL,
        captured_at TEXT NOT NULL,
        FOREIGN KEY(record_id) REFERENCES prediction_lifecycle_records(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prediction_combo_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        combo_key TEXT NOT NULL UNIQUE,
        combo_type TEXT NOT NULL,
        legs_json TEXT NOT NULL,
        quality REAL,
        combined_odds REAL,
        result TEXT,
        profit REAL,
        status TEXT NOT NULL DEFAULT 'pending',
        captured_at TEXT NOT NULL,
        settled_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prediction_knowledge_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        knowledge_key TEXT NOT NULL UNIQUE,
        fixture_id INTEGER NOT NULL,
        record_id INTEGER,
        market_id TEXT,
        outcome TEXT NOT NULL,
        reason TEXT,
        confidence REAL,
        quality_score REAL,
        engine TEXT,
        knowledge_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(record_id) REFERENCES prediction_lifecycle_records(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_plc_knowledge_fixture
    ON prediction_knowledge_records(fixture_id, created_at DESC)
    """,
)
