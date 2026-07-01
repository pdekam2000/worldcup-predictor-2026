#!/usr/bin/env python3
"""Validate HOTFIX WC-RESULT-SYNC-2 — ECSE snapshot automatic result sync."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.clients.api_football import ApiCallResult
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.database.connection import connect, init_database
from worldcup_predictor.database.migrations import ensure_schema_compat
from worldcup_predictor.quota.local_first import should_bypass_stale_local_fixture
from worldcup_predictor.research.ecse_live.ddl import PHASE_ECSE_LIVE_DDL
from worldcup_predictor.research.ecse_live.evaluator import run_ecse_evaluations
from worldcup_predictor.research.ecse_live.result_sync import (
    provider_status_is_finished,
    scan_ecse_snapshot_result_candidates,
    sync_ecse_snapshot_results,
)
from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables, insert_snapshot

CHECKS: list[tuple[str, bool, str]] = []
TEST_FIXTURE_ID = 9_900_002
TEST_SNAPSHOT_ID = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def _seed_db(conn: sqlite3.Connection) -> None:
    for ddl in PHASE_ECSE_LIVE_DDL:
        conn.execute(ddl)
    conn.commit()

    past = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO competitions(key, name, league_id, season, competition_type,
            supports_groups, supports_table, updated_at)
        VALUES ('world_cup_2026', 'World Cup 2026', 732, 2026, 'world_cup_finals', 1, 1, ?)
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO fixtures(fixture_id, competition_key, home_team, away_team,
            kickoff_utc, status, is_placeholder, source, updated_at)
        VALUES (?, 'world_cup_2026', 'Alpha', 'Beta', ?, 'NS', 0, 'cache', ?)
        """,
        (TEST_FIXTURE_ID, past, now),
    )
    conn.commit()

    _, reason = insert_snapshot(
        conn,
        {
            "fixture_id": TEST_FIXTURE_ID,
            "competition_key": "world_cup_2026",
            "home_team": "Alpha",
            "away_team": "Beta",
            "kickoff_utc": past,
            "model_version": "test",
            "lambda_home": 1.2,
            "lambda_away": 0.9,
            "top_10_scorelines": [{"scoreline": "1-0", "rank": 1, "probability": 0.2}],
            "top_1_score": "1-0",
            "top_3_scores": ["1-0", "2-0", "1-1"],
            "top_5_scores": ["1-0", "2-0", "1-1", "2-1", "0-0"],
            "confidence_score": 0.5,
            "data_quality_score": 0.8,
        },
    )
    assert reason in {"inserted", "already_exists", "duplicate"}


def _finished_api_item(*, status: str = "FT", home: int = 2, away: int = 1) -> list[dict]:
    return [
        {
            "fixture": {
                "id": TEST_FIXTURE_ID,
                "date": (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat(),
                "status": {"short": status, "long": "Match Finished"},
                "venue": {"name": "Test", "city": "Test"},
            },
            "teams": {
                "home": {"name": "Alpha", "id": 1},
                "away": {"name": "Beta", "id": 2},
            },
            "league": {"id": 732, "season": 2026, "round": "Round of 32"},
            "goals": {"home": home, "away": away},
            "score": {
                "halftime": {"home": 1, "away": 0},
                "fulltime": {"home": home, "away": away},
                "penalty": {"home": 3, "away": 4} if status == "PEN" else {"home": None, "away": None},
            },
        }
    ]


def _live_api_item() -> list[dict]:
    return [
        {
            "fixture": {
                "id": TEST_FIXTURE_ID,
                "date": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                "status": {"short": "1H", "long": "First Half"},
                "venue": {"name": "Test", "city": "Test"},
            },
            "teams": {
                "home": {"name": "Alpha", "id": 1},
                "away": {"name": "Beta", "id": 2},
            },
            "league": {"id": 732, "season": 2026, "round": "Round of 32"},
            "goals": {"home": 0, "away": 0},
            "score": {"halftime": {"home": 0, "away": 0}},
        }
    ]


def main() -> int:
    print("validate_ecse_snapshot_result_sync")
    settings = Settings(API_FOOTBALL_KEY="test-key", SQLITE_PATH=":memory:")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        conn = init_database(db_path)
        try:
            _seed_db(conn)

            candidates = scan_ecse_snapshot_result_candidates(
                conn,
                competition_key="world_cup_2026",
                past_only=True,
                min_hours_since_kickoff=0,
                fixture_ids=[TEST_FIXTURE_ID],
                settings=settings,
            )
            check(
                "ecse_only_candidate_discovered",
                any(c.fixture_id == TEST_FIXTURE_ID for c in candidates),
                f"count={len(candidates)}",
            )
            cand = next((c for c in candidates if c.fixture_id == TEST_FIXTURE_ID), None)
            check(
                "candidate_has_snapshot_fields",
                bool(cand and cand.snapshot_id and cand.kickoff_time),
                str(cand.to_dict() if cand else None),
            )

            check("stale_ns_local_bypass", should_bypass_stale_local_fixture({
                "status": "NS",
                "kickoff_utc": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
            }))
            check("finished_local_no_bypass", not should_bypass_stale_local_fixture({
                "status": "FT",
                "kickoff_utc": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
            }))
            check("provider_ft_finished", provider_status_is_finished("FT"))
            check("provider_pen_finished", provider_status_is_finished("PEN"))
            check("provider_live_not_finished", not provider_status_is_finished("1H"))

            finished_payload = _finished_api_item(status="FT")
            api_mod = __import__(
                "worldcup_predictor.clients.api_football",
                fromlist=["ApiFootballClient"],
            )
            with patch.object(api_mod.ApiFootballClient, "_safe_get", return_value=ApiCallResult(
                data=finished_payload, source="live", endpoint="fixtures",
            )):
                sync_out = sync_ecse_snapshot_results(
                    settings=Settings(API_FOOTBALL_KEY="test-key", SQLITE_PATH=str(db_path)),
                    competition_key="world_cup_2026",
                    fixture_ids=[TEST_FIXTURE_ID],
                    min_hours_since_kickoff=0,
                    dry_run=False,
                    force=True,
                    run_ecse_backfill=True,
                )
            check("finished_provider_persisted", sync_out.synced >= 1, f"synced={sync_out.synced}")

            row = conn.execute(
                "SELECT status FROM fixtures WHERE fixture_id = ?", (TEST_FIXTURE_ID,)
            ).fetchone()
            result = conn.execute(
                "SELECT final_score, match_outcome_type, penalty_score FROM fixture_results WHERE fixture_id = ?",
                (TEST_FIXTURE_ID,),
            ).fetchone()
            check("fixture_status_ft", row and row["status"] == "FT", str(dict(row) if row else None))
            check("result_row_exists", result is not None)
            check(
                "final_score_type_stored",
                result and result["match_outcome_type"] == "FT",
                str(dict(result) if result else None),
            )

            eval_count = conn.execute(
                "SELECT COUNT(*) AS c FROM ecse_prediction_evaluations WHERE fixture_id = ?",
                (TEST_FIXTURE_ID,),
            ).fetchone()["c"]
            check("ecse_evaluation_created", eval_count == 1, f"count={eval_count}")

            with patch.object(api_mod.ApiFootballClient, "_safe_get", return_value=ApiCallResult(
                data=finished_payload, source="live", endpoint="fixtures",
            )):
                dup = sync_ecse_snapshot_results(
                    settings=Settings(API_FOOTBALL_KEY="test-key", SQLITE_PATH=str(db_path)),
                    competition_key="world_cup_2026",
                    fixture_ids=[TEST_FIXTURE_ID],
                    min_hours_since_kickoff=0,
                    dry_run=False,
                    force=False,
                    run_ecse_backfill=True,
                )
            eval_count_2 = conn.execute(
                "SELECT COUNT(*) AS c FROM ecse_prediction_evaluations WHERE fixture_id = ?",
                (TEST_FIXTURE_ID,),
            ).fetchone()["c"]
            check(
                "no_duplicate_evaluations",
                eval_count_2 == 1,
                f"count={eval_count_2}, skipped={dup.skipped}",
            )

            conn.execute("UPDATE fixtures SET status = 'NS' WHERE fixture_id = ?", (TEST_FIXTURE_ID,))
            conn.execute("DELETE FROM fixture_results WHERE fixture_id = ?", (TEST_FIXTURE_ID,))
            conn.execute(
                "DELETE FROM ecse_prediction_evaluations WHERE fixture_id = ?",
                (TEST_FIXTURE_ID,),
            )
            conn.commit()

            with patch.object(api_mod.ApiFootballClient, "_safe_get", return_value=ApiCallResult(
                data=_live_api_item(), source="live", endpoint="fixtures",
            )):
                live_sync = sync_ecse_snapshot_results(
                    settings=Settings(API_FOOTBALL_KEY="test-key", SQLITE_PATH=str(db_path)),
                    competition_key="world_cup_2026",
                    fixture_ids=[TEST_FIXTURE_ID],
                    min_hours_since_kickoff=0,
                    dry_run=False,
                    force=True,
                    run_ecse_backfill=False,
                )
            live_result = conn.execute(
                "SELECT 1 FROM fixture_results WHERE fixture_id = ?",
                (TEST_FIXTURE_ID,),
            ).fetchone()
            check(
                "non_finished_not_persisted",
                live_result is None and live_sync.pending_provider >= 1,
                f"pending={live_sync.pending_provider}",
            )

            with patch.object(api_mod.ApiFootballClient, "_safe_get", return_value=ApiCallResult(
                data=_finished_api_item(status="PEN", home=1, away=1),
                source="live",
                endpoint="fixtures",
            )):
                sync_ecse_snapshot_results(
                    settings=Settings(API_FOOTBALL_KEY="test-key", SQLITE_PATH=str(db_path)),
                    competition_key="world_cup_2026",
                    fixture_ids=[TEST_FIXTURE_ID],
                    min_hours_since_kickoff=0,
                    dry_run=False,
                    force=True,
                    run_ecse_backfill=False,
                )
            pen_row = conn.execute(
                "SELECT final_score, match_outcome_type, penalty_score FROM fixture_results WHERE fixture_id = ?",
                (TEST_FIXTURE_ID,),
            ).fetchone()
            check(
                "pen_fixture_handled",
                pen_row and pen_row["match_outcome_type"] == "PEN" and pen_row["penalty_score"] == "3-4",
                str(dict(pen_row) if pen_row else None),
            )

            refresh_src = (
                ROOT / "worldcup_predictor/automation/worldcup_background/result_refresh.py"
            ).read_text(encoding="utf-8")
            check("wde_refresh_includes_ecse_sync", "refresh_ecse_snapshot_results" in refresh_src)
            check(
                "ecse_baseline_unchanged",
                "INSERT INTO ecse_prediction_snapshots" in (
                    ROOT / "worldcup_predictor/research/ecse_live/store.py"
                ).read_text(encoding="utf-8"),
            )
            check("no_public_prediction_changes", "prediction_output" not in refresh_src)
        finally:
            conn.close()

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    failed = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"\n{passed}/{len(CHECKS)} passed, {failed} failed")
    out = ROOT / "artifacts" / "validate_ecse_snapshot_result_sync.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in CHECKS],
                "passed": passed,
                "failed": failed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    exit_code = 0 if failed == 0 else 1

    import gc

    gc.collect()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
