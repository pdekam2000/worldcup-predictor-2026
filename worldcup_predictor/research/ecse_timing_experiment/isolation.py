"""Isolation preflight for MID/LATE timing snapshots."""

from __future__ import annotations

import sqlite3
from typing import Any

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.research.canonical_ephemeral.constants import EXECUTION_MODE
from worldcup_predictor.research.canonical_ephemeral.facade import run_ephemeral_canonical_prediction
from worldcup_predictor.research.canonical_ephemeral.types import ResearchContext
from worldcup_predictor.research.canonical_ephemeral.write_guard import ephemeral_mode_active
from worldcup_predictor.research.ecse_timing_experiment.db import connect_timing_db, timing_db_path
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot


def _count(conn: sqlite3.Connection, table: str) -> int:
    try:
        row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
        return int(row["c"] if row and "c" in row.keys() else row[0])
    except Exception:
        return -1


def _freeze_hashes(eval_conn: sqlite3.Connection, fixture_ids: list[int]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for fid in fixture_ids:
        row = eval_conn.execute(
            """
            SELECT content_hash, prediction_id FROM frozen_predictions
            WHERE fixture_id=? ORDER BY frozen_at ASC LIMIT 1
            """,
            (int(fid),),
        ).fetchone()
        if not row:
            out[str(fid)] = None
        else:
            out[str(fid)] = str(row["content_hash"] or row["prediction_id"])
    return out


def snapshot_canonical_state(fixture_ids: list[int]) -> dict[str, Any]:
    settings = get_settings()
    prod = connect(settings.sqlite_path)
    eval_conn = connect_eval_db(project_root())
    try:
        return {
            "wsp_count": _count(prod, "worldcup_stored_predictions"),
            "ecse_count": _count(prod, "ecse_prediction_snapshots"),
            "freeze_count": _count(eval_conn, "frozen_predictions"),
            "freeze_hashes": _freeze_hashes(eval_conn, fixture_ids),
        }
    finally:
        prod.close()
        eval_conn.close()


def run_isolation_preflight(
    *,
    experiment_id: str,
    experiment_date: str,
    snapshot_class: str,
    fixture_ids: list[int],
    audit_id: str,
) -> dict[str, Any]:
    """Hard gate for MID/LATE. Returns ok=False with BLOCKED_RESEARCH_ISOLATION_NOT_PROVEN on failure."""
    sc = snapshot_class.upper()
    if sc == "EARLY":
        return {"ok": True, "skipped": True, "reason": "early_does_not_require_preflight"}

    failures: list[str] = []
    if not fixture_ids:
        failures.append("no_fixtures")

    timing_path = timing_db_path()
    if not timing_path.parent.exists():
        failures.append("research_db_parent_missing")
    try:
        tconn = connect_timing_db()
        tconn.execute("SELECT 1 FROM timing_experiments LIMIT 1")
        tconn.close()
    except Exception as exc:
        failures.append(f"research_db_not_writable:{exc}")

    before = snapshot_canonical_state(fixture_ids)
    # Dry-run ephemeral on first fixture with fresh odds if available
    settings = get_settings()
    prod = connect(settings.sqlite_path)
    dry_fixture = int(fixture_ids[0]) if fixture_ids else None
    dry_result = None
    try:
        if dry_fixture:
            row = prod.execute(
                "SELECT kickoff_utc FROM fixtures WHERE fixture_id=? LIMIT 1", (dry_fixture,)
            ).fetchone()
            ko = row["kickoff_utc"] if row else None
            odds = get_latest_valid_1x2_odds_snapshot(prod, dry_fixture, kickoff_utc=ko)
            if odds is None:
                failures.append("fresh_odds_unavailable_for_dry_run")
            else:
                ctx = ResearchContext(
                    experiment_id=experiment_id,
                    experiment_date=experiment_date,
                    snapshot_class=sc,
                    audit_id=audit_id,
                    scope="owner",
                    caller="ecse_timing_experiment",
                )
                # Prove guard context works
                dry_result = run_ephemeral_canonical_prediction(
                    dry_fixture,
                    scope="owner",
                    odds_snapshot=odds,
                    research_context=ctx,
                    settings=settings,
                    prod_conn=prod,
                )
                if dry_result.execution_mode != EXECUTION_MODE:
                    failures.append("ephemeral_mode_not_active_in_result")
                if dry_result.canonical_writes_completed != 0:
                    failures.append("canonical_writes_completed_nonzero")
                if dry_result.wsp_written or dry_result.ecse_canonical_written or dry_result.freeze_created:
                    failures.append("canonical_write_flags_set")
                if not dry_result.complete and dry_result.quality_status not in {"OK", "PARTIAL", "BLOCKED", "FAILED"}:
                    failures.append("dry_run_no_result")
    except Exception as exc:
        failures.append(f"ephemeral_dry_run_failed:{type(exc).__name__}:{exc}")
    finally:
        prod.close()

    after = snapshot_canonical_state(fixture_ids)
    if before["wsp_count"] != after["wsp_count"]:
        failures.append("wsp_count_changed")
    if before["ecse_count"] != after["ecse_count"]:
        failures.append("ecse_count_changed")
    if before["freeze_count"] != after["freeze_count"]:
        failures.append("freeze_count_changed")
    if before["freeze_hashes"] != after["freeze_hashes"]:
        failures.append("freeze_hashes_changed")

    # ephemeral_mode_active should be false outside the call
    if ephemeral_mode_active():
        failures.append("ephemeral_context_leaked")

    ok = not failures
    return {
        "ok": ok,
        "status": "OK" if ok else "BLOCKED_RESEARCH_ISOLATION_NOT_PROVEN",
        "failures": failures,
        "before": before,
        "after": after,
        "dry_run_fixture_id": dry_fixture,
        "dry_run_complete": None if dry_result is None else dry_result.complete,
        "dry_run_execution_mode": None if dry_result is None else dry_result.execution_mode,
        "ephemeral_required": True,
        "write_guard_required": True,
    }
