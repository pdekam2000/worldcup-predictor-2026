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


# Phase 45B — evaluation trust / quarantine metadata
PHASE45B_EVAL_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("worldcup_prediction_evaluations", "is_quarantined", "INTEGER NOT NULL DEFAULT 0"),
    ("worldcup_prediction_evaluations", "evaluation_source", "TEXT NOT NULL DEFAULT 'production'"),
    ("worldcup_prediction_evaluations", "quarantine_reason", "TEXT"),
)

# Phase 36C — stored prediction invalidation metadata
PHASE36C_WC_STORED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("worldcup_stored_predictions", "is_active", "INTEGER NOT NULL DEFAULT 1"),
    ("worldcup_stored_predictions", "invalidated_at", "TEXT"),
    ("worldcup_stored_predictions", "invalidated_reason", "TEXT"),
    ("worldcup_stored_predictions", "superseded_by", "INTEGER"),
)

# Phase 46B — historical legacy import metadata (stored-prediction quarantine)
PHASE46B_STORED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("worldcup_stored_predictions", "imported_at", "TEXT"),
    ("worldcup_stored_predictions", "import_source", "TEXT"),
    ("worldcup_stored_predictions", "quality_score", "REAL"),
    ("worldcup_stored_predictions", "is_quarantined", "INTEGER NOT NULL DEFAULT 0"),
    ("worldcup_stored_predictions", "quarantine_reason", "TEXT"),
)

# Phase 46C-1 — advanced evaluation outcome persistence on fixture_results
PHASE46C1_RESULT_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("fixture_results", "ht_home_goals", "INTEGER"),
    ("fixture_results", "ht_away_goals", "INTEGER"),
    ("fixture_results", "ht_result", "TEXT"),
    ("fixture_results", "first_goal_team", "TEXT"),
    ("fixture_results", "first_goal_player", "TEXT"),
    ("fixture_results", "first_goal_minute", "INTEGER"),
    ("fixture_results", "first_goal_extra_minute", "INTEGER"),
    ("fixture_results", "match_outcome_type", "TEXT"),
    ("fixture_results", "outcome_persisted_at", "TEXT"),
    ("fixture_results", "outcome_source", "TEXT"),
)

# Phase 46C-2 — advanced market evaluation status columns
PHASE46C2_EVAL_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("worldcup_prediction_evaluations", "market_ht_status", "TEXT"),
    ("worldcup_prediction_evaluations", "market_cs_status", "TEXT"),
    ("worldcup_prediction_evaluations", "market_fg_team_status", "TEXT"),
    ("worldcup_prediction_evaluations", "market_goalscorer_status", "TEXT"),
)

# Phase 46C-3 — goal minute evaluation columns
PHASE46C3_EVAL_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("worldcup_prediction_evaluations", "market_goal_minute_status", "TEXT"),
    ("worldcup_prediction_evaluations", "market_goal_minute_actual", "TEXT"),
    ("worldcup_prediction_evaluations", "market_goal_minute_predicted", "TEXT"),
)

PHASE48A_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS performance_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        competition_key TEXT NOT NULL DEFAULT 'world_cup_2026',
        snapshot_at TEXT NOT NULL,
        evaluated_count INTEGER NOT NULL DEFAULT 0,
        correct_count INTEGER NOT NULL DEFAULT 0,
        wrong_count INTEGER NOT NULL DEFAULT 0,
        pending_count INTEGER NOT NULL DEFAULT 0,
        overall_winrate REAL,
        markets_json TEXT NOT NULL,
        rule_a_json TEXT,
        agent_contribution_json TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_performance_snapshots_at
    ON performance_snapshots(competition_key, snapshot_at DESC)
    """,
)

# Phase 46D — unified provider event layer
PHASE46D_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS fixture_unified_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        sort_index INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        minute INTEGER,
        extra_minute INTEGER,
        team TEXT,
        team_id INTEGER,
        player TEXT,
        assist TEXT,
        detail TEXT,
        source TEXT NOT NULL DEFAULT 'merged',
        is_penalty INTEGER NOT NULL DEFAULT 0,
        is_own_goal INTEGER NOT NULL DEFAULT 0,
        card_type TEXT,
        sub_in TEXT,
        sub_out TEXT,
        UNIQUE(fixture_id, sort_index),
        FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_fixture_unified_events_fixture
    ON fixture_unified_events(fixture_id)
    """,
)

PHASE46C1_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS fixture_goal_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        sort_index INTEGER NOT NULL,
        minute INTEGER,
        extra_minute INTEGER,
        team TEXT,
        team_id INTEGER,
        player TEXT,
        assist TEXT,
        is_penalty INTEGER NOT NULL DEFAULT 0,
        is_own_goal INTEGER NOT NULL DEFAULT 0,
        detail TEXT,
        UNIQUE(fixture_id, sort_index),
        FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_fixture_goal_events_fixture
    ON fixture_goal_events(fixture_id)
    """,
)

# Phase 62B — World Cup fixture competition_type + Sportmonks mapping
# HOTFIX WC-RESULT-SYNC-2 — penalty shootout score separate from match aggregate
WC_RESULT_SYNC_2_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("fixture_results", "penalty_score", "TEXT"),
)

PHASE62B_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("fixtures", "competition_type", "TEXT NOT NULL DEFAULT 'world_cup_finals'"),
)

PHASE62B_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS wc_fixture_mapping (
        api_football_fixture_id INTEGER PRIMARY KEY,
        sportmonks_fixture_id INTEGER,
        mapping_confidence REAL,
        mapping_source TEXT,
        date_match INTEGER NOT NULL DEFAULT 0,
        team_match INTEGER NOT NULL DEFAULT 0,
        blocked INTEGER NOT NULL DEFAULT 0,
        block_reason TEXT,
        mapped_at TEXT NOT NULL,
        FOREIGN KEY (api_football_fixture_id) REFERENCES fixtures(fixture_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_wc_fixture_mapping_sm
    ON wc_fixture_mapping(sportmonks_fixture_id)
    """,
)

# Phase 61 — autonomous prediction snapshots (immutable append-only)
PHASE61_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS autonomous_prediction_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_key TEXT NOT NULL UNIQUE,
        fixture_id INTEGER NOT NULL,
        competition_key TEXT NOT NULL,
        season INTEGER,
        league_id INTEGER,
        home_team TEXT,
        away_team TEXT,
        kickoff_utc TEXT,
        fixture_status TEXT,
        engine TEXT NOT NULL,
        market_id TEXT NOT NULL,
        prediction_json TEXT NOT NULL,
        confidence REAL,
        tier TEXT,
        odds_decimal REAL,
        generated_by TEXT NOT NULL DEFAULT 'autonomous_scheduler',
        source TEXT NOT NULL,
        is_user_visible INTEGER NOT NULL DEFAULT 0,
        is_immutable INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        payload_hash TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_autonomous_snap_fixture
    ON autonomous_prediction_snapshots(fixture_id, engine, created_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS autonomous_snapshot_evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_id INTEGER NOT NULL UNIQUE,
        fixture_id INTEGER NOT NULL,
        engine TEXT NOT NULL,
        market_id TEXT NOT NULL,
        status TEXT NOT NULL,
        evaluation_reason TEXT,
        actual_json TEXT,
        evaluated_at TEXT NOT NULL,
        FOREIGN KEY(snapshot_id) REFERENCES autonomous_prediction_snapshots(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_autonomous_eval_fixture
    ON autonomous_snapshot_evaluations(fixture_id, engine, evaluated_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS autonomous_certification_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_at TEXT NOT NULL,
        report_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS autonomous_cycle_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,
        report_json TEXT
    )
    """,
)

# Phase 33 — background World Cup stored predictions + evaluations
PHASE44_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS worldcup_stored_predictions (
        fixture_id INTEGER PRIMARY KEY,
        competition_key TEXT NOT NULL DEFAULT 'world_cup_2026',
        kickoff_utc TEXT,
        payload_json TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'background',
        predicted_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_wc_stored_pred_kickoff
    ON worldcup_stored_predictions(kickoff_utc)
    """,
    """
    CREATE TABLE IF NOT EXISTS worldcup_prediction_evaluations (
        fixture_id INTEGER PRIMARY KEY,
        competition_key TEXT NOT NULL DEFAULT 'world_cup_2026',
        overall_status TEXT NOT NULL DEFAULT 'pending',
        no_bet INTEGER NOT NULL DEFAULT 0,
        actual_result TEXT,
        final_score TEXT,
        safe_pick_status TEXT,
        value_pick_status TEXT,
        aggressive_pick_status TEXT,
        market_1x2_status TEXT,
        market_ou_status TEXT,
        market_btts_status TEXT,
        market_dc_status TEXT,
        detail_json TEXT,
        evaluated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS worldcup_accuracy_summary (
        competition_key TEXT PRIMARY KEY,
        summary_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
)

# Phase 34 — learning reports + usage tracking
PHASE45_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS learning_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        competition_key TEXT NOT NULL DEFAULT 'world_cup_2026',
        report_type TEXT NOT NULL DEFAULT 'advisory_v1',
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_learning_reports_created
    ON learning_reports(created_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS user_daily_prediction_usage (
        user_id TEXT NOT NULL,
        usage_date TEXT NOT NULL,
        fixture_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (user_id, usage_date, fixture_id)
    )
    """,
)

# Phase 32C — national team form/H2H history caches
PHASE43_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS fixture_team_resolution (
        fixture_id INTEGER PRIMARY KEY,
        home_team_id INTEGER,
        away_team_id INTEGER,
        resolution_source TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS national_team_form_cache (
        team_id INTEGER PRIMARY KEY,
        team_name TEXT NOT NULL,
        matches_used INTEGER NOT NULL DEFAULT 0,
        last5_json TEXT,
        last10_json TEXT,
        home_json TEXT,
        away_json TEXT,
        neutral_json TEXT,
        recent_fixtures_json TEXT,
        national_form_score REAL,
        explanation_json TEXT,
        source TEXT NOT NULL DEFAULT 'cache_backfill',
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS national_team_h2h_cache (
        pair_key TEXT PRIMARY KEY,
        home_team_id INTEGER NOT NULL,
        away_team_id INTEGER NOT NULL,
        meetings_used INTEGER NOT NULL DEFAULT 0,
        meetings_json TEXT,
        national_h2h_score REAL,
        detail_json TEXT,
        source TEXT NOT NULL DEFAULT 'cache_backfill',
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_national_h2h_team_pair
    ON national_team_h2h_cache(home_team_id, away_team_id)
    """,
)

# Phase A15 — PredOps queue + immutable prediction snapshots
PHASE_A15_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS predops_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_key TEXT NOT NULL UNIQUE,
        fixture_id INTEGER NOT NULL,
        competition_key TEXT NOT NULL,
        kickoff_utc TEXT,
        priority_band INTEGER NOT NULL DEFAULT 5,
        status TEXT NOT NULL DEFAULT 'queued',
        attempts INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 3,
        failure_reason TEXT,
        trigger_reason TEXT,
        next_retry_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_predops_queue_status_prio
    ON predops_queue(status, priority_band, kickoff_utc)
    """,
    """
    CREATE TABLE IF NOT EXISTS predops_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_id TEXT NOT NULL UNIQUE,
        fixture_id INTEGER NOT NULL,
        competition_key TEXT NOT NULL,
        kickoff_utc TEXT,
        generated_at TEXT NOT NULL,
        trigger_reason TEXT,
        previous_snapshot_id TEXT,
        payload_json TEXT NOT NULL,
        markets_json TEXT NOT NULL,
        egie_json TEXT,
        deltas_json TEXT,
        coverage_state TEXT NOT NULL DEFAULT 'completed',
        engine_version TEXT,
        is_latest INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_predops_snap_fixture_time
    ON predops_snapshots(fixture_id, generated_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_predops_snap_latest
    ON predops_snapshots(fixture_id, is_latest)
    """,
    """
    CREATE TABLE IF NOT EXISTS predops_scheduler_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,
        report_json TEXT
    )
    """,
)

# Phase A18 — Paper betting simulator (virtual only)
PHASE_A18_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS paper_betting_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        starting_bankroll REAL NOT NULL,
        current_bankroll REAL NOT NULL,
        currency TEXT NOT NULL DEFAULT 'EUR',
        risk_profile TEXT NOT NULL DEFAULT 'balanced',
        month TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(user_id, month)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_paper_accounts_user
    ON paper_betting_accounts(user_id, month DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS paper_betting_bets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        account_id INTEGER NOT NULL,
        fixture_id INTEGER NOT NULL,
        competition_key TEXT,
        home_team TEXT,
        away_team TEXT,
        market TEXT NOT NULL,
        prediction TEXT NOT NULL,
        stake REAL NOT NULL,
        odds_decimal REAL,
        odds_estimated INTEGER NOT NULL DEFAULT 0,
        bet_quality_score REAL,
        combo_type TEXT,
        combo_group_id TEXT,
        source_page TEXT,
        snapshot_id TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        settlement_reason TEXT,
        profit_loss REAL,
        settled_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(account_id) REFERENCES paper_betting_accounts(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_paper_bets_user_status
    ON paper_betting_bets(user_id, status, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_paper_bets_fixture
    ON paper_betting_bets(fixture_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS paper_betting_settlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bet_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        status TEXT NOT NULL,
        profit_loss REAL,
        payout REAL,
        odds_used REAL,
        evaluation_source TEXT,
        settled_at TEXT NOT NULL,
        reason TEXT,
        FOREIGN KEY(bet_id) REFERENCES paper_betting_bets(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_paper_settlements_bet
    ON paper_betting_settlements(bet_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS paper_betting_monthly_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        month TEXT NOT NULL,
        report_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(user_id, month)
    )
    """,
)

PHASE_A19_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS assistant_watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        item_type TEXT NOT NULL,
        item_id TEXT NOT NULL,
        item_name TEXT,
        item_meta TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(user_id, item_type, item_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_assistant_watchlist_user
    ON assistant_watchlist(user_id, created_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS assistant_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        category TEXT NOT NULL,
        alert_type TEXT NOT NULL,
        fixture_id INTEGER,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        reason TEXT,
        link TEXT,
        is_read INTEGER NOT NULL DEFAULT 0,
        dedup_key TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_assistant_notif_user
    ON assistant_notifications(user_id, is_read, created_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS assistant_preferences (
        user_id TEXT PRIMARY KEY,
        prefs_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assistant_alert_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope_key TEXT NOT NULL UNIQUE,
        last_value TEXT,
        last_snapshot_id TEXT,
        updated_at TEXT NOT NULL
    )
    """,
)

PHASE_A20_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS social_share_links (
        share_id TEXT PRIMARY KEY,
        user_id TEXT,
        share_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        og_title TEXT,
        og_description TEXT,
        is_public INTEGER NOT NULL DEFAULT 1,
        opt_in INTEGER NOT NULL DEFAULT 0,
        expires_at TEXT,
        created_at TEXT NOT NULL,
        view_count INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_social_share_type
    ON social_share_links(share_type, created_at DESC)
    """,
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

    for ddl in PHASE43_DDL:
        conn.execute(ddl)

    for table, column, typedef in PHASE36C_WC_STORED_COLUMNS:
        if _table_exists(conn, table):
            _add_column_if_missing(conn, table, column, typedef)

    for table, column, typedef in PHASE45B_EVAL_COLUMNS:
        if _table_exists(conn, table):
            _add_column_if_missing(conn, table, column, typedef)

    for table, column, typedef in PHASE46B_STORED_COLUMNS:
        if _table_exists(conn, table):
            _add_column_if_missing(conn, table, column, typedef)

    for ddl in PHASE46C1_DDL:
        conn.execute(ddl)

    for table, column, typedef in PHASE46C1_RESULT_COLUMNS:
        if _table_exists(conn, table):
            _add_column_if_missing(conn, table, column, typedef)

    for table, column, typedef in PHASE46C2_EVAL_COLUMNS:
        if _table_exists(conn, table):
            _add_column_if_missing(conn, table, column, typedef)

    for table, column, typedef in PHASE46C3_EVAL_COLUMNS:
        if _table_exists(conn, table):
            _add_column_if_missing(conn, table, column, typedef)

    for table, column, typedef in PHASE62B_COLUMNS:
        if _table_exists(conn, table):
            _add_column_if_missing(conn, table, column, typedef)

    for table, column, typedef in WC_RESULT_SYNC_2_COLUMNS:
        if _table_exists(conn, table):
            _add_column_if_missing(conn, table, column, typedef)

    for ddl in PHASE62B_DDL:
        conn.execute(ddl)

    for ddl in PHASE48A_DDL:
        conn.execute(ddl)

    for ddl in PHASE46D_DDL:
        conn.execute(ddl)

    for ddl in PHASE61_DDL:
        conn.execute(ddl)

    try:
        from worldcup_predictor.research.ecse_live.ddl import PHASE_ECSE_LIVE_DDL

        for ddl in PHASE_ECSE_LIVE_DDL:
            conn.execute(ddl)
    except ModuleNotFoundError:
        pass

    try:
        from worldcup_predictor.research.safe_bets.ddl import PHASE_SAFE_BETS_DDL

        for ddl in PHASE_SAFE_BETS_DDL:
            conn.execute(ddl)
    except ModuleNotFoundError:
        pass

    try:
        from worldcup_predictor.research.goal_timing_split.ddl import PHASE_GOAL_TIMING_SPLIT_DDL

        for ddl in PHASE_GOAL_TIMING_SPLIT_DDL:
            conn.execute(ddl)
    except ModuleNotFoundError:
        pass

    try:
        from worldcup_predictor.research.ecse_x2_m1.build import ensure_ecse_score_distributions_m1_table

        ensure_ecse_score_distributions_m1_table(conn)
    except ModuleNotFoundError:
        pass

    for ddl in PHASE44_DDL:
        conn.execute(ddl)

    for ddl in PHASE45_DDL:
        conn.execute(ddl)

    for ddl in PHASE_A15_DDL:
        conn.execute(ddl)

    for ddl in PHASE_A18_DDL:
        conn.execute(ddl)

    for ddl in PHASE_A19_DDL:
        conn.execute(ddl)

    for ddl in PHASE_A20_DDL:
        conn.execute(ddl)

    try:
        from worldcup_predictor.lifecycle.ddl import PHASE_A23_DDL

        for ddl in PHASE_A23_DDL:
            conn.execute(ddl)
    except ModuleNotFoundError:
        pass

    try:
        from worldcup_predictor.providers.oddalerts_historical_odds import PHASE_OA2_DDL

        for ddl in PHASE_OA2_DDL:
            conn.execute(ddl)
    except ModuleNotFoundError:
        pass

    try:
        from worldcup_predictor.data_import.european_fixture_feed import EURO_FIXTURE_FEED_DDL

        for ddl in EURO_FIXTURE_FEED_DDL:
            conn.execute(ddl)
    except ModuleNotFoundError:
        pass

    try:
        from worldcup_predictor.data_import.oddalerts_enrichment_ddl import ODDALERTS_ENRICHMENT_DDL

        for ddl in ODDALERTS_ENRICHMENT_DDL:
            conn.execute(ddl)
    except ModuleNotFoundError:
        pass

    try:
        from worldcup_predictor.data_import.oddalerts_csv_incremental_ddl import ODDALERTS_INBOX_CATALOG_DDL

        for ddl in ODDALERTS_INBOX_CATALOG_DDL:
            conn.execute(ddl)
    except ModuleNotFoundError:
        pass

    try:
        from worldcup_predictor.data_import.oddalerts_probability_market_ddl import ODDALERTS_PROBABILITY_MARKET_DDL

        for ddl in ODDALERTS_PROBABILITY_MARKET_DDL:
            conn.execute(ddl)
    except ModuleNotFoundError:
        pass

    try:
        from worldcup_predictor.research.oddalerts_ecse_shadow_ddl import ECSE_ODDALERTS_SHADOW_DDL

        for ddl in ECSE_ODDALERTS_SHADOW_DDL:
            conn.execute(ddl)
    except ModuleNotFoundError:
        pass

    try:
        from worldcup_predictor.research.oddalerts_ecse_monitor_ddl import ECSE_ODDALERTS_MONITOR_DDL

        for ddl in ECSE_ODDALERTS_MONITOR_DDL:
            conn.execute(ddl)
    except ModuleNotFoundError:
        pass

    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )
    conn.commit()


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Legacy entry point — always runs idempotent schema compatibility checks."""
    ensure_schema_compat(conn)
