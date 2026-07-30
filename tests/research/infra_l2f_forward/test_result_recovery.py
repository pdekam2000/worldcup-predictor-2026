"""Unit tests for Phase 3 result recovery classification and cohort separation."""

from __future__ import annotations

import sqlite3

from worldcup_predictor.research.infra_l2f_forward.result_recovery import (
    CLASS_ALREADY_PRESENT,
    CLASS_CONFLICT,
    CLASS_NOT_FINISHED,
    CLASS_POSTPONED,
    CLASS_PROVIDER_UNAVAILABLE,
    CLASS_RECOVERED_DB,
    CLASS_RECOVERED_PROVIDER,
    classify_sync_outcome,
)
from worldcup_predictor.research.infra_l2f_forward.historical_replay import (
    COHORT_HISTORICAL,
    EVAL_TABLE,
    ensure_replay_schema,
)
from worldcup_predictor.research.infra_l2f_forward.result_recovery import COHORT_RECOVERED
from worldcup_predictor.research.infra_l2f_forward.high_goal_detector import DetectorRule, _apply_rule


def test_classify_sync_outcomes():
    assert classify_sync_outcome({"reused": True, "reason": "eval_actual_result_exists"}, used_provider=False) == CLASS_ALREADY_PRESENT
    assert classify_sync_outcome({"synced": True, "result_available": True, "status": "ok"}, used_provider=False) == CLASS_RECOVERED_DB
    assert classify_sync_outcome({"synced": True, "result_available": True, "status": "ok"}, used_provider=True) == CLASS_RECOVERED_PROVIDER
    assert classify_sync_outcome({"conflict": True, "reason": "regulation_score_conflict"}, used_provider=False) == CLASS_CONFLICT
    assert classify_sync_outcome({"reason": "provider_not_finished", "result_available": False}, used_provider=True) == CLASS_NOT_FINISHED
    assert classify_sync_outcome({"result_quality_status": "POSTPONED", "reason": "postponed"}, used_provider=False) == CLASS_POSTPONED
    assert classify_sync_outcome({"reason": "api_football_not_configured", "result_available": False}, used_provider=True) == CLASS_PROVIDER_UNAVAILABLE


def test_detector_ignores_final_goals_as_input():
    rule = DetectorRule(name="t", description="t", min_expected_total=2.75, min_tail_mass=None)
    row = {
        "expected_total_lambda": 3.1,
        "actual_total_goals": 0,  # low final goals must not block prematch gate
        "balanced_prematch": True,
    }
    assert _apply_rule(row, rule) is True
    row2 = {"expected_total_lambda": 2.0, "actual_total_goals": 6}
    assert _apply_rule(row2, rule) is False


def test_cohort_separation_eval_table(tmp_path):
    conn = sqlite3.connect(tmp_path / "fi.db")
    ensure_replay_schema(conn)
    conn.execute(
        f"""
        INSERT INTO {EVAL_TABLE} (
            eval_id, fixture_id, freeze_id, model_id, model_version, run_id, cohort_type,
            actual_home, actual_away, created_at_utc
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        ("a", 1, "f1", "EXACT_V2_SELECTED", "1", "r", COHORT_HISTORICAL, 1, 1, "t"),
    )
    conn.execute(
        f"""
        INSERT INTO {EVAL_TABLE} (
            eval_id, fixture_id, freeze_id, model_id, model_version, run_id, cohort_type,
            actual_home, actual_away, created_at_utc
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        ("b", 2, "f2", "EXACT_V2_SELECTED", "1", "r", COHORT_RECOVERED, 2, 2, "t"),
    )
    conn.commit()
    n_h = conn.execute(
        f"SELECT COUNT(*) FROM {EVAL_TABLE} WHERE cohort_type=?", (COHORT_HISTORICAL,)
    ).fetchone()[0]
    n_r = conn.execute(
        f"SELECT COUNT(*) FROM {EVAL_TABLE} WHERE cohort_type=?", (COHORT_RECOVERED,)
    ).fetchone()[0]
    assert n_h == 1 and n_r == 1


def test_classify_idempotent_reused():
    a = classify_sync_outcome({"reused": True, "reason": "eval_actual_result_exists"}, used_provider=True)
    b = classify_sync_outcome({"reused": True, "reason": "eval_actual_result_exists"}, used_provider=False)
    assert a == b == CLASS_ALREADY_PRESENT
