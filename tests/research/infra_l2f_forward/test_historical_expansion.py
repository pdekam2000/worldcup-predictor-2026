"""Tests for historical cohort eligibility, leakage, and replay dry-run."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from worldcup_predictor.research.infra_l2f_forward.historical_cohort import (
    CLASS_BLOCKED_MISSING_RESULT,
    CLASS_BLOCKED_POSTKICKOFF,
    CLASS_ELIGIBLE_HISTORICAL,
    CLASS_ELIGIBLE_TRUE_FORWARD,
    classify_row,
    inventory_eval_db,
)
from worldcup_predictor.research.infra_l2f_forward.historical_replay import (
    COHORT_HISTORICAL,
    run_historical_replay_batch,
)
from worldcup_predictor.research.infra_l2f_forward.leakage_checks import (
    assert_prediction_before_kickoff,
    payload_contains_result_leakage,
)


def _eval_db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "eval.db")
    conn.executescript(
        """
        CREATE TABLE frozen_predictions (
          prediction_id TEXT PRIMARY KEY,
          fixture_id INTEGER,
          kickoff TEXT,
          frozen_at TEXT,
          prediction_scope TEXT,
          validation_tier TEXT,
          competition TEXT,
          freeze_status TEXT,
          quarantine_reason TEXT,
          lambda_home REAL,
          lambda_away REAL
        );
        CREATE TABLE actual_results (
          fixture_id INTEGER PRIMARY KEY,
          actual_home_goals INTEGER,
          actual_away_goals INTEGER,
          actual_score TEXT
        );
        """
    )
    # eligible historical
    conn.execute(
        "INSERT INTO frozen_predictions VALUES ('fz1',1,'2026-06-01T18:00:00','2026-06-01T12:00:00','production','A','liga','ACTIVE',NULL,1.4,1.1)"
    )
    conn.execute("INSERT INTO actual_results VALUES (1,2,1,'2-1')")
    # postkickoff contamination
    conn.execute(
        "INSERT INTO frozen_predictions VALUES ('fz2',2,'2026-06-02T18:00:00','2026-06-02T19:00:00','production','A','liga','ACTIVE',NULL,1.2,1.0)"
    )
    conn.execute("INSERT INTO actual_results VALUES (2,1,0,'1-0')")
    # missing result
    conn.execute(
        "INSERT INTO frozen_predictions VALUES ('fz3',3,'2026-06-03T18:00:00','2026-06-03T12:00:00','owner_shadow','B','liga','ACTIVE',NULL,1.3,1.2)"
    )
    # true forward (future kickoff)
    conn.execute(
        "INSERT INTO frozen_predictions VALUES ('fz4',4,'2099-01-01T18:00:00','2098-12-31T12:00:00','owner_shadow','B','liga','ACTIVE',NULL,1.5,1.0)"
    )
    conn.commit()
    return conn


def test_classify_helpers():
    assert classify_row(
        freeze_status="ACTIVE",
        quarantine_reason=None,
        scope="production",
        lh=1.2,
        la=1.1,
        kickoff="2026-01-01T18:00:00",
        frozen_at="2026-01-01T12:00:00",
        has_result=True,
    )[0] == CLASS_ELIGIBLE_HISTORICAL
    assert classify_row(
        freeze_status="ACTIVE",
        quarantine_reason=None,
        scope="production",
        lh=1.2,
        la=1.1,
        kickoff="2026-01-01T18:00:00",
        frozen_at="2026-01-01T19:00:00",
        has_result=True,
    )[0] == CLASS_BLOCKED_POSTKICKOFF
    assert classify_row(
        freeze_status="ACTIVE",
        quarantine_reason=None,
        scope="production",
        lh=1.2,
        la=1.1,
        kickoff="2026-01-01T18:00:00",
        frozen_at="2026-01-01T12:00:00",
        has_result=False,
    )[0] == CLASS_BLOCKED_MISSING_RESULT
    assert classify_row(
        freeze_status="ACTIVE",
        quarantine_reason=None,
        scope="owner_shadow",
        lh=1.2,
        la=1.1,
        kickoff="2099-01-01T18:00:00",
        frozen_at="2098-12-31T12:00:00",
        has_result=False,
    )[0] == CLASS_ELIGIBLE_TRUE_FORWARD


def test_inventory_and_dry_run(tmp_path):
    eval_conn = _eval_db(tmp_path)
    cands = inventory_eval_db(eval_conn)
    hist = [c for c in cands if c.classification == CLASS_ELIGIBLE_HISTORICAL]
    assert len(hist) == 1
    assert hist[0].fixture_id == 1
    fi = sqlite3.connect(tmp_path / "fi.db")
    batch = run_historical_replay_batch(
        eval_conn=eval_conn,
        fi_conn=fi,
        batch_size=10,
        dry_run=True,
        cohort=COHORT_HISTORICAL,
        disk_line="/dev/sda1 75G 60G 12G 84% /",
    )
    assert batch.processed == 1
    assert batch.details[0]["status"] == "dry_run_eligible"
    # disk stop
    stopped = run_historical_replay_batch(
        eval_conn=eval_conn,
        fi_conn=fi,
        batch_size=10,
        dry_run=True,
        disk_line="/dev/sda1 75G 70G 7.5G 90% /",
        min_free_gb=8.0,
    )
    assert stopped.stopped_reason and "disk_free" in stopped.stopped_reason
    fi.close()
    eval_conn.close()


def test_leakage_guards():
    assert assert_prediction_before_kickoff("2026-01-01T12:00:00", "2026-01-01T18:00:00") is None
    assert assert_prediction_before_kickoff("2026-01-01T19:00:00", "2026-01-01T18:00:00") == "frozen_at_not_before_kickoff"
    assert payload_contains_result_leakage({"meta": {"actual_home_goals": 2}}) is True
    assert payload_contains_result_leakage({"meta": {"lambda_home": 1.2}}) is False
