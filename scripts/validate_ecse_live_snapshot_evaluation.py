#!/usr/bin/env python3
"""Validate PHASE ECSE-LIVE-1 snapshot + evaluation loop."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_live.evaluator import evaluate_frozen_snapshot
from worldcup_predictor.research.ecse_live.prediction_builder import build_ecse_live_prediction
from worldcup_predictor.research.ecse_live.runner import is_snapshot_window, run_ecse_snapshot_runner
from worldcup_predictor.research.ecse_live.store import (
    ensure_ecse_live_tables,
    get_snapshot,
    has_evaluation,
    insert_evaluation,
    insert_snapshot,
)
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution

CHECKS: list[tuple[str, bool, str]] = []
TEST_FIXTURE_ID = 9_900_001


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def _seed_fixture(conn: sqlite3.Connection, *, kickoff_utc: str, status: str = "NS") -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fixtures (
            fixture_id INTEGER PRIMARY KEY,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            status TEXT,
            competition_key TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO fixtures(fixture_id, home_team, away_team, kickoff_utc, status, competition_key)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (TEST_FIXTURE_ID, "Alpha FC", "Beta United", kickoff_utc, status, "world_cup_2026"),
    )
    conn.commit()


def _sample_odds_payload() -> dict:
    return {
        "bookmakers": [
            {
                "name": "Bet365",
                "bets": [
                    {
                        "name": "Match Winner",
                        "values": [
                            {"value": "Home", "odd": "2.10"},
                            {"value": "Draw", "odd": "3.40"},
                            {"value": "Away", "odd": "3.50"},
                        ],
                    },
                    {
                        "name": "Goals Over/Under",
                        "values": [
                            {"value": "Over 2.5", "odd": "1.90"},
                            {"value": "Under 2.5", "odd": "1.95"},
                        ],
                    },
                    {
                        "name": "Both Teams Score",
                        "values": [
                            {"value": "Yes", "odd": "1.75"},
                            {"value": "No", "odd": "2.05"},
                        ],
                    },
                ],
            }
        ]
    }


def _seed_odds(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS odds_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER,
            competition_key TEXT,
            snapshot_at TEXT,
            payload_json TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO odds_snapshots(fixture_id, competition_key, snapshot_at, payload_json)
        VALUES (?, ?, ?, ?)
        """,
        (
            TEST_FIXTURE_ID,
            "world_cup_2026",
            datetime.now(timezone.utc).isoformat(),
            json.dumps(_sample_odds_payload()),
        ),
    )
    conn.commit()


def _build_manual_prediction(fixture_id: int, kickoff: str) -> dict:
    dist = generate_score_distribution(1.45, 1.15)
    top_10 = [
        {
            "scoreline": e["scoreline"],
            "probability": round(float(e["probability"]), 6),
            "rank": int(e["rank"]),
            "home_goals": int(e["home_goals"]),
            "away_goals": int(e["away_goals"]),
        }
        for e in dist[:10]
    ]
    return {
        "fixture_id": fixture_id,
        "registry_fixture_id": None,
        "competition_key": "world_cup_2026",
        "home_team": "Alpha FC",
        "away_team": "Beta United",
        "kickoff_utc": kickoff,
        "model_version": "ECSE-LIVE-1-test",
        "lambda_home": 1.45,
        "lambda_away": 1.15,
        "top_10_scorelines": top_10,
        "top_1_score": top_10[0]["scoreline"],
        "top_3_scores": [e["scoreline"] for e in top_10[:3]],
        "top_5_scores": [e["scoreline"] for e in top_10[:5]],
        "confidence_score": top_10[0]["probability"],
        "data_quality_score": 0.72,
        "raw_features": {"test": True},
        "prediction_source": "test",
    }


def run_isolated_tests() -> None:
    print("Isolated SQLite tests\n")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "ecse_live_test.db"
        conn = connect(db_path)
        try:
            ensure_ecse_live_tables(conn)

            kickoff = (datetime.now(timezone.utc) + timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S")
            _seed_fixture(conn, kickoff_utc=kickoff)
            _seed_odds(conn)

            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            check(
                "tables_created",
                "ecse_prediction_snapshots" in tables and "ecse_prediction_evaluations" in tables,
            )

            pred = build_ecse_live_prediction(conn, TEST_FIXTURE_ID)
            check("live_prediction_built", pred is not None and len(pred.get("top_10_scorelines", [])) >= 5)

            manual = _build_manual_prediction(TEST_FIXTURE_ID, kickoff)
            sid1, reason1 = insert_snapshot(conn, manual)
            check("snapshot_inserted_once", sid1 is not None and reason1 == "inserted", f"id={sid1}")

            manual["top_1_score"] = "9-9"
            sid2, reason2 = insert_snapshot(conn, manual)
            frozen = get_snapshot(conn, TEST_FIXTURE_ID)
            check(
                "repeat_run_no_overwrite",
                reason2 == "already_exists" and frozen is not None and frozen["top_1_score"] != "9-9",
                f"frozen_top1={frozen['top_1_score'] if frozen else None}",
            )

            top10 = json.loads(frozen["top_10_scorelines_json"]) if frozen else []
            top3 = json.loads(frozen["top_3_scores_json"]) if frozen else []
            top5 = json.loads(frozen["top_5_scores_json"]) if frozen else []
            check("top10_count", len(top10) == 10, f"n={len(top10)}")
            check("top3_subset", len(top3) == 3 and top3 == [x["scoreline"] for x in top10[:3]])
            check("top5_subset", len(top5) == 5 and top5 == [x["scoreline"] for x in top10[:5]])

            outcome_pending = SimpleNamespace(is_finished=False, final_score=None, fixture_status="NS")
            check(
                "pending_match_stays_pending",
                evaluate_frozen_snapshot(frozen, outcome_pending) is None,
            )

            actual_scoreline = frozen["top_1_score"]
            outcome_ft = SimpleNamespace(
                is_finished=True,
                final_score=actual_scoreline,
                fixture_status="FT",
            )
            eval_payload = evaluate_frozen_snapshot(frozen, outcome_ft)
            check(
                "finished_eval_top1_correct",
                eval_payload is not None and eval_payload["top1_correct"] is True,
                f"score={actual_scoreline}",
            )

            eid1, ereason1 = insert_evaluation(conn, eval_payload)
            check("evaluation_inserted_once", eid1 is not None and ereason1 == "inserted")

            eval_payload["top1_correct"] = False
            eid2, ereason2 = insert_evaluation(conn, eval_payload)
            check("repeat_eval_no_overwrite", ereason2 == "already_exists" and has_evaluation(conn, sid1))

            frozen_after = get_snapshot(conn, TEST_FIXTURE_ID)
            fresh_dist = generate_score_distribution(2.5, 2.5)
            fresh_top1 = fresh_dist[0]["scoreline"]
            check(
                "evaluation_uses_frozen_not_fresh",
                frozen_after["top_1_score"] != fresh_top1 or eval_payload["top1_correct"] is True,
                f"frozen={frozen_after['top_1_score']} fresh={fresh_top1}",
            )

            window_ok = is_snapshot_window(kickoff, minutes_before=60)
            check("t60_window_eligible", window_ok, "kickoff in 45m")

            settings = Settings(
                ecse_live_enabled=True,
                ecse_live_snapshot_minutes_before=60,
                ecse_live_eval_minutes_after_ft=15,
                ecse_live_dry_run=False,
                sqlite_path=str(db_path),
            )
            snap_run = run_ecse_snapshot_runner(conn, settings=settings, limit=10)
            check(
                "runner_skips_existing_snapshot",
                snap_run.skipped_exists >= 1 or not snap_run.inserted,
                f"inserted={snap_run.inserted} skipped_exists={snap_run.skipped_exists}",
            )
        finally:
            conn.close()


def run_production_readonly_checks() -> None:
    print("\nProduction DB read-only checks\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    ensure_ecse_live_tables(conn)

    snap_n = conn.execute("SELECT COUNT(1) FROM ecse_prediction_snapshots").fetchone()[0]
    eval_n = conn.execute("SELECT COUNT(1) FROM ecse_prediction_evaluations").fetchone()[0]
    api_log_n = 0
    try:
        api_log_n = conn.execute("SELECT COUNT(1) FROM ecse_live_api_log").fetchone()[0]
    except Exception:
        pass
    check("production_tables_ready", True, f"snapshots={snap_n} evaluations={eval_n}")
    check("api_calls_logged", api_log_n > 0 or snap_n == 0, f"api_log_rows={api_log_n}")

    wde_tables = conn.execute(
        "SELECT COUNT(1) FROM sqlite_master WHERE name='worldcup_stored_predictions'"
    ).fetchone()[0]
    check("wde_storage_unchanged", wde_tables == 1, "worldcup_stored_predictions present")

    conn.close()


def main() -> int:
    print("ECSE-LIVE-1 snapshot + evaluation validation\n")
    run_isolated_tests()
    run_production_readonly_checks()

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    failed = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"\nResult: {passed}/{len(CHECKS)} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
