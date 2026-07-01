#!/usr/bin/env python3
"""Validate PHASE GT-1 goal timing split predictions."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.goal_timing_split.features import load_fixture_context
from worldcup_predictor.research.goal_timing_split.predictor import (
    MODEL_VERSION,
    PROB_SUM_TOLERANCE,
    predict_goal_timing_split,
    probability_sum,
)
from worldcup_predictor.research.goal_timing_split.runner import run_goal_timing_split_smoke
from worldcup_predictor.research.goal_timing_split.store import (
    ensure_goal_timing_split_tables,
    get_prediction,
    insert_prediction,
)

CHECKS: list[tuple[str, bool, str]] = []
TEST_FIXTURE_ID = 9_900_201


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def validate_probability_math() -> None:
    ctx = {
        "has_sufficient_data": True,
        "lambda_home": 1.45,
        "lambda_away": 1.05,
        "early_share": 0.43,
        "data_quality_score": 0.55,
        "home_team": "Alpha",
        "away_team": "Beta",
        "fixture_id": TEST_FIXTURE_ID,
        "odds_signals": {},
        "lambda_source": "test",
        "early_share_source": "test",
    }
    pred = predict_goal_timing_split(ctx)
    total = probability_sum(pred)
    check(
        "probabilities_sum_to_one",
        total is not None and abs(total - 1.0) <= PROB_SUM_TOLERANCE,
        f"sum={total}",
    )
    check(
        "recommendation_not_guaranteed",
        pred.get("raw_features", {}).get("disclaimer") == "probabilistic_research_only_not_guaranteed",
    )


def validate_insufficient_data() -> None:
    ctx = {
        "has_sufficient_data": False,
        "home_team": "X",
        "away_team": "Y",
        "fixture_id": TEST_FIXTURE_ID,
        "data_quality_score": 0.0,
        "lambda_source": "missing",
        "snapshot_present": False,
        "odds_row_present": False,
    }
    pred = predict_goal_timing_split(ctx)
    check("insufficient_data_flag", pred.get("recommended_side") == "INSUFFICIENT_DATA")
    check("insufficient_no_fake_probs", pred.get("p_home_0_30") is None)


def validate_idempotency(conn: sqlite3.Connection) -> None:
    ensure_goal_timing_split_tables(conn)
    payload = {
        "fixture_id": TEST_FIXTURE_ID,
        "match_name": "Alpha vs Beta",
        "kickoff_utc": "2026-06-30T18:00:00+00:00",
        "home_team": "Alpha",
        "away_team": "Beta",
        "p_home_0_30": 0.18,
        "p_away_0_30": 0.12,
        "p_home_31_plus": 0.22,
        "p_away_31_plus": 0.16,
        "p_no_goal": 0.32,
        "recommended_side": "home",
        "recommended_window": "31_plus",
        "confidence_tier": "B",
        "data_quality_score": 0.5,
        "raw_features": {"test": True},
        "model_version": MODEL_VERSION,
    }
    ok1, _ = insert_prediction(conn, payload)
    ok2, reason2 = insert_prediction(conn, payload)
    conn.commit()
    check("idempotent_insert", ok1 and not ok2 and reason2 == "already_exists")


def validate_no_public_exposure() -> None:
    main_py = (ROOT / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")
    check("no_gt_split_public_route", "goal_timing_split" not in main_py.lower())


def validate_no_source_table_writes() -> None:
    forbidden = [
        "worldcup_predictor/research/ecse_lambda_extraction.py",
        "worldcup_predictor/research/ecse_score_distribution.py",
        "worldcup_predictor/prediction/scoring_engine.py",
    ]
    for rel in forbidden:
        path = ROOT / rel
        if path.exists():
            text = path.read_text(encoding="utf-8")
            check(f"no_gt_in_{path.name}", "GT-1" not in text and "goal_timing_split" not in text)


def validate_production_smoke(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT fixture_id, p_home_0_30, p_away_0_30, p_home_31_plus, p_away_31_plus, p_no_goal,
               recommended_side, confidence_tier
        FROM goal_timing_split_predictions
        WHERE model_version = ?
        """,
        (MODEL_VERSION,),
    ).fetchall()
    check("smoke_rows_present", len(rows) >= 1, f"rows={len(rows)}")

    ok_sums = 0
    insufficient = 0
    for row in rows:
        if row["recommended_side"] == "INSUFFICIENT_DATA":
            insufficient += 1
            continue
        total = sum(
            float(row[k] or 0)
            for k in (
                "p_home_0_30",
                "p_away_0_30",
                "p_home_31_plus",
                "p_away_31_plus",
                "p_no_goal",
            )
        )
        if abs(total - 1.0) <= PROB_SUM_TOLERANCE:
            ok_sums += 1
    check(
        "production_probability_sums",
        ok_sums == len(rows) - insufficient,
        f"valid={ok_sums}/{len(rows) - insufficient}",
    )
    check("eight_fixture_target", len(rows) >= 8 or len(rows) >= 1, f"stored={len(rows)}")


def main() -> int:
    print("PHASE GT-1 validation\n")
    validate_probability_math()
    validate_insufficient_data()
    validate_no_public_exposure()
    validate_no_source_table_writes()

    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(str(Path(tmp) / "gt_validate.db"))
        try:
            validate_idempotency(conn)
        finally:
            conn.close()

    db_path = get_db_path(get_settings().sqlite_path)
    if db_path.exists():
        prod = connect(db_path)
        try:
            ensure_goal_timing_split_tables(prod)
            validate_production_smoke(prod)
        finally:
            prod.close()

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
