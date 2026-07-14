"""Phase 7B — Isolated evaluation SQLite database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.forward_evaluation.constants import EVAL_DB_RELATIVE

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS evaluation_batches (
        batch_id TEXT PRIMARY KEY,
        evaluation_date TEXT NOT NULL,
        timezone TEXT NOT NULL,
        created_at TEXT NOT NULL,
        discovered_count INTEGER NOT NULL DEFAULT 0,
        eligible_count INTEGER NOT NULL DEFAULT 0,
        frozen_count INTEGER NOT NULL DEFAULT 0,
        excluded_count INTEGER NOT NULL DEFAULT 0,
        evaluated_count INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        batch_hash TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS frozen_predictions (
        prediction_id TEXT PRIMARY KEY,
        batch_id TEXT NOT NULL,
        fixture_id INTEGER NOT NULL,
        match_name TEXT NOT NULL,
        competition TEXT,
        tier TEXT,
        kickoff TEXT,
        generated_at TEXT,
        frozen_at TEXT NOT NULL,
        prediction_mode TEXT,
        odds_timestamp TEXT,
        odds_home REAL,
        odds_draw REAL,
        odds_away REAL,
        bookmaker_count INTEGER,
        odds_freshness TEXT,
        wde_decision TEXT,
        ft_marginal_direction TEXT,
        home_probability REAL,
        draw_probability REAL,
        away_probability REAL,
        wde_confidence REAL,
        effective_1x2 TEXT,
        btts_prediction TEXT,
        btts_probability REAL,
        ou25_prediction TEXT,
        over_probability REAL,
        under_probability REAL,
        top3_mass REAL,
        top5_mass REAL,
        top10_mass REAL,
        entropy REAL,
        lambda_home REAL,
        lambda_away REAL,
        total_lambda REAL,
        market_direction TEXT,
        consensus TEXT,
        data_quality TEXT,
        warning_summary TEXT,
        wde_model_version TEXT,
        ecse_model_version TEXT,
        ecse_top5_complete INTEGER NOT NULL DEFAULT 1,
        payload_hash TEXT NOT NULL,
        evaluation_status TEXT NOT NULL DEFAULT 'PENDING',
        UNIQUE(fixture_id, payload_hash)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS exact_score_rankings (
        prediction_id TEXT NOT NULL,
        fixture_id INTEGER NOT NULL,
        rank INTEGER NOT NULL,
        score TEXT NOT NULL,
        probability REAL,
        PRIMARY KEY (prediction_id, rank)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS excluded_candidates (
        batch_id TEXT NOT NULL,
        fixture_id INTEGER NOT NULL,
        match_name TEXT,
        competition TEXT,
        tier TEXT,
        kickoff TEXT,
        exclusion_reason TEXT NOT NULL,
        detail_json TEXT,
        PRIMARY KEY (batch_id, fixture_id, exclusion_reason)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS actual_results (
        fixture_id INTEGER PRIMARY KEY,
        result_status TEXT NOT NULL,
        actual_home_goals INTEGER,
        actual_away_goals INTEGER,
        actual_score TEXT,
        actual_1x2 TEXT,
        actual_btts TEXT,
        actual_ou25 TEXT,
        finished_at TEXT,
        result_source TEXT,
        score_basis TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS market_evaluations (
        prediction_id TEXT PRIMARY KEY,
        fixture_id INTEGER NOT NULL,
        wde_hit TEXT,
        ft_marginal_hit TEXT,
        effective_1x2_hit TEXT,
        btts_hit TEXT,
        ou25_hit TEXT,
        ecse_top1_hit TEXT,
        ecse_top3_hit TEXT,
        ecse_top5_hit TEXT,
        actual_score_rank TEXT,
        actual_score_probability REAL,
        evaluation_timestamp TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prediction_context (
        prediction_id TEXT PRIMARY KEY,
        competition TEXT,
        tier TEXT,
        odds_regime TEXT,
        entropy_bucket TEXT,
        top3_mass_bucket TEXT,
        top5_mass_bucket TEXT,
        conflict_class TEXT,
        market_agreement_class TEXT,
        data_quality_class TEXT,
        freshness_class TEXT,
        bookmaker_count_bucket TEXT,
        lambda_bucket TEXT,
        favorite_class TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_frozen_fixture ON frozen_predictions(fixture_id)",
    "CREATE INDEX IF NOT EXISTS idx_frozen_status ON frozen_predictions(evaluation_status)",
    "CREATE INDEX IF NOT EXISTS idx_frozen_batch ON frozen_predictions(batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_market_eval_fixture ON market_evaluations(fixture_id)",
)


def eval_db_path(root: Path | None = None) -> Path:
    base = root or project_root()
    return (base / EVAL_DB_RELATIVE).resolve()


def connect_eval_db(root: Path | None = None) -> sqlite3.Connection:
    path = eval_db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


_FREEZE_V2_MIGRATIONS = (
    "ALTER TABLE frozen_predictions ADD COLUMN provider_fixture_id INTEGER",
    "ALTER TABLE frozen_predictions ADD COLUMN league_id INTEGER",
    "ALTER TABLE frozen_predictions ADD COLUMN season TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN home_team_name TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN away_team_name TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN prediction_scope TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN public_visible INTEGER DEFAULT 1",
    "ALTER TABLE frozen_predictions ADD COLUMN worldcup_stored_prediction_id INTEGER",
    "ALTER TABLE frozen_predictions ADD COLUMN ecse_snapshot_id INTEGER",
    "ALTER TABLE frozen_predictions ADD COLUMN source_job_id TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN odds_snapshot_id INTEGER",
    "ALTER TABLE frozen_predictions ADD COLUMN source_commit_sha TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN source_payload_hash TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN content_hash TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN odds_fetched_at_utc TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN last_valid_prematch_time_utc TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN prediction_engine_version TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN btts_model_version TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN ou_model_version TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN odds_freshness_status TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN wde_payload_json TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN btts_payload_json TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN ou_payload_json TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN ecse_payload_json TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN complete_payload_json TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN immutable INTEGER DEFAULT 1",
    "ALTER TABLE frozen_predictions ADD COLUMN freeze_version TEXT DEFAULT 'FORWARD-FREEZE-v2'",
    "ALTER TABLE frozen_predictions ADD COLUMN supersedes_freeze_id TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN freeze_status TEXT DEFAULT 'ACTIVE'",
    "ALTER TABLE frozen_predictions ADD COLUMN wde_execution_status TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN btts_execution_status TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN ou_execution_status TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN unavailable_fields_json TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN quarantine_reason TEXT",
)

_FREEZE_V2_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_frozen_scope ON frozen_predictions(prediction_scope, evaluation_status)",
    "CREATE INDEX IF NOT EXISTS idx_frozen_kickoff ON frozen_predictions(kickoff)",
    "CREATE INDEX IF NOT EXISTS idx_frozen_ecse_snapshot ON frozen_predictions(ecse_snapshot_id)",
    "CREATE INDEX IF NOT EXISTS idx_frozen_wsp ON frozen_predictions(worldcup_stored_prediction_id)",
    "CREATE INDEX IF NOT EXISTS idx_frozen_content_hash ON frozen_predictions(content_hash)",
    "CREATE INDEX IF NOT EXISTS idx_frozen_source_hash ON frozen_predictions(source_payload_hash)",
)

_FREEZE_QUARANTINE_DDL = """
CREATE TABLE IF NOT EXISTS freeze_quarantine (
    fixture_id INTEGER NOT NULL,
    prediction_scope TEXT,
    reason TEXT NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (fixture_id, reason)
)
"""

_SCHEMA_MIGRATIONS = (
    "ALTER TABLE frozen_predictions ADD COLUMN validation_tier TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN display_status TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN competition_family TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN domain_type TEXT",
    "ALTER TABLE frozen_predictions ADD COLUMN validation_note TEXT",
    "ALTER TABLE prediction_context ADD COLUMN validation_tier TEXT",
    "ALTER TABLE prediction_context ADD COLUMN display_status TEXT",
    "ALTER TABLE prediction_context ADD COLUMN competition_family TEXT",
    "ALTER TABLE prediction_context ADD COLUMN domain_type TEXT",
    *_FREEZE_V2_MIGRATIONS,
)


def ensure_schema(conn: sqlite3.Connection) -> None:
    for ddl in _DDL:
        conn.execute(ddl)
    for migration in _SCHEMA_MIGRATIONS:
        try:
            conn.execute(migration)
        except sqlite3.OperationalError:
            pass
    conn.execute(_FREEZE_QUARANTINE_DDL)
    for idx in _FREEZE_V2_INDEXES:
        try:
            conn.execute(idx)
        except sqlite3.OperationalError:
            pass
    conn.commit()


def schema_column_names(conn: sqlite3.Connection, table: str = "frozen_predictions") -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(r[1]) for r in rows]
