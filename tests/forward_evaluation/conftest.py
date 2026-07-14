"""Shared fixtures for forward evaluation freeze service tests."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from worldcup_predictor.forward_evaluation.db import ensure_schema
from worldcup_predictor.research.ecse_live.ddl import PHASE_ECSE_LIVE_DDL


def _utc_offset(days: float = 1.0) -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _utc_past(days: float = 2.0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


@pytest.fixture
def prod_db(tmp_path):
    path = tmp_path / "prod.db"
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE fixtures (
            fixture_id INTEGER PRIMARY KEY,
            competition_key TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            status TEXT,
            season INTEGER,
            league_id INTEGER,
            is_placeholder INTEGER DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE worldcup_stored_predictions (
            fixture_id INTEGER PRIMARY KEY,
            competition_key TEXT,
            kickoff_utc TEXT,
            payload_json TEXT,
            source TEXT,
            predicted_at TEXT,
            updated_at TEXT,
            is_active INTEGER DEFAULT 1,
            is_quarantined INTEGER DEFAULT 0,
            prediction_scope TEXT,
            validation_tier TEXT,
            source_runtime TEXT
        )
        """
    )
    for ddl in PHASE_ECSE_LIVE_DDL:
        conn.execute(ddl)
    for col in ("prediction_scope", "validation_tier", "source_runtime"):
        try:
            conn.execute(f"ALTER TABLE ecse_prediction_snapshots ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def eval_db(tmp_path):
    path = tmp_path / "eval.db"
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    yield conn
    conn.close()


def seed_tier_a_fixture(
    prod_conn: sqlite3.Connection,
    *,
    fixture_id: int = 900001,
    kickoff_days_ahead: float = 2.0,
    predicted_days_ahead: float = 1.0,
    tier_source: str = "owner_daily_predictions",
    scope_hint: str | None = None,
    stale_odds: bool = False,
    missing_wde: bool = False,
    missing_ecse_top5: bool = False,
    post_kickoff_predicted: bool = False,
) -> dict:
    kickoff = _utc_offset(kickoff_days_ahead)
    predicted = _utc_offset(predicted_days_ahead) if not post_kickoff_predicted else _utc_offset(kickoff_days_ahead + 0.1)

    prod_conn.execute(
        """
        INSERT OR REPLACE INTO fixtures
        (fixture_id, competition_key, home_team, away_team, kickoff_utc, status, season, league_id, is_placeholder)
        VALUES (?, 'world_cup_2026', 'Alpha FC', 'Beta FC', ?, 'NS', 2026, 1, 0)
        """,
        (fixture_id, kickoff),
    )

    payload = {
        "probabilities": {"home_win": 0.45, "draw": 0.28, "away_win": 0.27},
        "effective_1x2": {"pick": "home_win", "decision_source": "wde"},
        "confidence_score": 62.0,
        "model_version": "WDE-v9",
        "extended_markets": {
            "btts": {"prediction": "yes", "yes_probability": 58.0},
            "over_under_25": {"prediction": "over", "over_probability": 54.0},
        },
        "odds_freshness": {
            "odds_freshness_class": "ODDS_STALE" if stale_odds else "FRESH",
            "canonical_odds_snapshot": {
                "fetched_at_utc": predicted,
                "odds_home": 2.1,
                "odds_draw": 3.4,
                "odds_away": 3.2,
                "bookmaker_count": 8,
                "provider": "test",
            },
        },
    }
    if missing_wde:
        payload = {"odds_freshness": payload["odds_freshness"]}

    prod_conn.execute(
        """
        INSERT OR REPLACE INTO worldcup_stored_predictions
        (fixture_id, competition_key, kickoff_utc, payload_json, source, predicted_at, updated_at, is_active, is_quarantined)
        VALUES (?, 'world_cup_2026', ?, ?, ?, ?, ?, 1, 0)
        """,
        (
            fixture_id,
            kickoff,
            json.dumps(payload),
            scope_hint or tier_source,
            predicted,
            predicted,
        ),
    )

    top5 = [
        {"rank": i, "scoreline": f"{i}-{i-1}", "probability": 0.12 - i * 0.01}
        for i in range(1, 6)
    ]
    if missing_ecse_top5:
        top5 = top5[:2]

    prod_conn.execute(
        """
        INSERT OR REPLACE INTO ecse_prediction_snapshots (
            id, snapshot_key, fixture_id, competition_key, home_team, away_team, kickoff_utc,
            generated_at, model_version, lambda_home, lambda_away, top_10_scorelines_json,
            top_1_score, top_3_scores_json, top_5_scores_json, confidence_score, data_quality_score,
            prediction_source, is_frozen
        ) VALUES (1, ?, ?, 'world_cup_2026', 'Alpha FC', 'Beta FC', ?, ?, 'ECSE-v3', 1.4, 1.1, ?, '1-0', ?, ?, 0.7, 0.8, ?, 1)
        """,
        (
            f"ecse-live:{fixture_id}",
            fixture_id,
            kickoff,
            predicted,
            json.dumps(top5),
            json.dumps(top5[:3]),
            json.dumps(top5),
            tier_source,
        ),
    )
    prod_conn.commit()
    return {"fixture_id": fixture_id, "kickoff": kickoff, "predicted": predicted}


def seed_tier_b_fixture(prod_conn: sqlite3.Connection, *, fixture_id: int = 900002) -> dict:
    meta = seed_tier_a_fixture(
        prod_conn,
        fixture_id=fixture_id,
        tier_source="tier_b_owner_shadow",
        scope_hint="tier_b_domestic",
    )
    prod_conn.execute(
        "UPDATE fixtures SET competition_key = 'allsvenskan' WHERE fixture_id = ?",
        (fixture_id,),
    )
    prod_conn.execute(
        "UPDATE worldcup_stored_predictions SET competition_key = 'allsvenskan' WHERE fixture_id = ?",
        (fixture_id,),
    )
    prod_conn.commit()
    return meta


def seed_fixture_result(
    prod_conn: sqlite3.Connection,
    *,
    fixture_id: int,
    home_goals: int = 2,
    away_goals: int = 1,
    status: str = "FT",
) -> None:
    prod_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fixture_results (
            fixture_id INTEGER PRIMARY KEY,
            competition_key TEXT,
            final_score TEXT,
            halftime_score TEXT,
            home_goals INTEGER,
            away_goals INTEGER,
            winner TEXT,
            over_under_2_5 TEXT,
            total_goals INTEGER,
            finished_at TEXT,
            source TEXT,
            regulation_home_goals INTEGER,
            regulation_away_goals INTEGER,
            final_stage TEXT,
            match_outcome_type TEXT
        )
        """
    )
    score = f"{home_goals}-{away_goals}"
    prod_conn.execute(
        """
        INSERT OR REPLACE INTO fixture_results (
            fixture_id, competition_key, final_score, home_goals, away_goals,
            regulation_home_goals, regulation_away_goals, final_stage, match_outcome_type,
            finished_at, source, total_goals, over_under_2_5, winner
        ) VALUES (?, 'world_cup_2026', ?, ?, ?, ?, ?, ?, ?, datetime('now'), 'test', ?, ?, ?)
        """,
        (
            fixture_id,
            score,
            home_goals,
            away_goals,
            home_goals,
            away_goals,
            status,
            status,
            home_goals + away_goals,
            "over_2_5" if home_goals + away_goals > 2 else "under_2_5",
            "home" if home_goals > away_goals else "draw",
        ),
    )
    prod_conn.execute(
        "UPDATE fixtures SET status=? WHERE fixture_id=?",
        (status, fixture_id),
    )
    prod_conn.commit()
