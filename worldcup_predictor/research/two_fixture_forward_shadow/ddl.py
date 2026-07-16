"""Additive DDL for two-fixture forward shadow portfolios (append-only freezes)."""

from __future__ import annotations

import sqlite3

PHASE_TFPS_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS tfps_fixture_eligibility (
        report_date TEXT NOT NULL,
        fixture_id INTEGER NOT NULL,
        eligibility TEXT NOT NULL,
        reasons_json TEXT,
        top5_mass REAL,
        entropy REAL,
        top5_priced_n INTEGER,
        kickoff_utc TEXT,
        updated_at_utc TEXT NOT NULL,
        PRIMARY KEY (report_date, fixture_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tfps_pair_candidates (
        pair_id TEXT PRIMARY KEY,
        report_date TEXT NOT NULL,
        fixture_a INTEGER NOT NULL,
        fixture_b INTEGER NOT NULL,
        selection_strategy TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        selection_timestamp_utc TEXT NOT NULL,
        pair_rank INTEGER NOT NULL,
        top5_mass_a REAL,
        top5_mass_b REAL,
        joint_top5_est REAL,
        entropy_a REAL,
        entropy_b REAL,
        league_a TEXT,
        league_b TEXT,
        odds_completeness TEXT,
        selected INTEGER NOT NULL DEFAULT 0,
        rejection_note TEXT,
        UNIQUE (report_date, fixture_a, fixture_b, selection_strategy, strategy_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tfps_portfolio_freezes (
        portfolio_id TEXT PRIMARY KEY,
        pair_id TEXT NOT NULL,
        report_date TEXT NOT NULL,
        frozen_at_utc TEXT NOT NULL,
        snapshot_window TEXT NOT NULL,
        bookmaker_mode TEXT NOT NULL,
        fixture_a INTEGER NOT NULL,
        fixture_b INTEGER NOT NULL,
        kickoff_a_utc TEXT,
        kickoff_b_utc TEXT,
        prediction_freeze_id_a TEXT,
        prediction_freeze_id_b TEXT,
        ecse_version TEXT,
        strategy_version TEXT NOT NULL,
        rule_version TEXT NOT NULL,
        hedge_policy_version TEXT NOT NULL,
        stake_version TEXT NOT NULL,
        odds_ingestion_version TEXT NOT NULL,
        cohort TEXT NOT NULL,
        stake_strategy TEXT NOT NULL,
        budget_eur REAL NOT NULL,
        total_primary_stake REAL NOT NULL,
        hedge_stake REAL NOT NULL,
        total_stake REAL NOT NULL,
        stakes_hypothetical INTEGER NOT NULL DEFAULT 1,
        primary_tickets_json TEXT NOT NULL,
        hedge_tickets_json TEXT NOT NULL,
        odds_timestamp_utc TEXT NOT NULL,
        bookmakers_json TEXT,
        expected_joint_coverage REAL,
        hedge_enhanced_coverage REAL,
        expected_value_est REAL,
        full_loss_prob_est REAL,
        min_covered_return REAL,
        max_return REAL,
        worst_case_loss REAL,
        source_hash TEXT NOT NULL,
        freeze_hash TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        betting_enabled INTEGER NOT NULL DEFAULT 0,
        UNIQUE (
            pair_id, snapshot_window, bookmaker_mode, stake_strategy,
            strategy_version, budget_eur
        )
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tfps_freezes_date
    ON tfps_portfolio_freezes(report_date, frozen_at_utc)
    """,
    """
    CREATE TABLE IF NOT EXISTS tfps_portfolio_evaluations (
        portfolio_id TEXT PRIMARY KEY,
        evaluated_at_utc TEXT NOT NULL,
        result_status TEXT NOT NULL,
        actual_score_a TEXT,
        actual_score_b TEXT,
        winning_ticket_id TEXT,
        gross_return REAL,
        net_return REAL,
        roi REAL,
        primary_hit INTEGER NOT NULL DEFAULT 0,
        hedge_hit INTEGER NOT NULL DEFAULT 0,
        full_loss INTEGER NOT NULL DEFAULT 0,
        recovery_class TEXT,
        regulation_time_only INTEGER NOT NULL DEFAULT 1,
        evaluation_notes TEXT,
        FOREIGN KEY (portfolio_id) REFERENCES tfps_portfolio_freezes(portfolio_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tfps_observability (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tfps_run_log (
        run_id TEXT PRIMARY KEY,
        job TEXT NOT NULL,
        started_at_utc TEXT NOT NULL,
        finished_at_utc TEXT,
        status TEXT NOT NULL,
        details_json TEXT
    )
    """,
)


def ensure_tfps_schema(conn: sqlite3.Connection) -> None:
    for ddl in PHASE_TFPS_DDL:
        conn.execute(ddl)
    conn.commit()
