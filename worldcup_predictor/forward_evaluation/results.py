"""Phase 7B Part H — Result sync from production database."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.forward_evaluation.constants import NON_TERMINAL_STATUSES, TERMINAL_STATUSES
from worldcup_predictor.outcomes.evaluation_score_policy import regulation_score_for_evaluation


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _result_row(prod_conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = prod_conn.execute(
        "SELECT * FROM fixture_results WHERE fixture_id = ? LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    if row:
        return dict(row)
    fx = prod_conn.execute(
        "SELECT fixture_id, status FROM fixtures WHERE fixture_id=?",
        (int(fixture_id),),
    ).fetchone()
    if not fx:
        return None
    data = dict(fx)
    return {
        "fixture_id": data["fixture_id"],
        "final_stage": data.get("status"),
        "match_outcome_type": data.get("status"),
    }


def _fixture_row(prod_conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = prod_conn.execute(
        "SELECT fixture_id, status FROM fixtures WHERE fixture_id=?",
        (int(fixture_id),),
    ).fetchone()
    return dict(row) if row else None


def is_evaluable_status(status: str | None) -> bool:
    s = str(status or "NS").upper()
    if s in NON_TERMINAL_STATUSES:
        return False
    return s in TERMINAL_STATUSES


def sync_actual_result(
    eval_conn: sqlite3.Connection,
    prod_conn: sqlite3.Connection,
    fixture_id: int,
) -> dict[str, Any]:
    fid = int(fixture_id)
    existing = eval_conn.execute(
        "SELECT fixture_id FROM actual_results WHERE fixture_id=?", (fid,)
    ).fetchone()
    if existing:
        return {"synced": False, "reason": "already_synced", "fixture_id": fid}

    result_row = _result_row(prod_conn, fid)
    fixture_row = _fixture_row(prod_conn, fid)
    status = str(
        (result_row or {}).get("final_stage")
        or (result_row or {}).get("match_outcome_type")
        or (fixture_row or {}).get("status")
        or "NS"
    ).upper()
    if not is_evaluable_status(status):
        return {"synced": False, "reason": "not_terminal", "fixture_id": fid, "status": status}

    home, away, scoreline, basis = regulation_score_for_evaluation(result_row, fixture_row)
    if home is None or away is None or not scoreline:
        return {"synced": False, "reason": "missing_regulation_score", "fixture_id": fid}

    total = int(home) + int(away)
    actual_1x2 = "home_win" if int(home) > int(away) else "away_win" if int(away) > int(home) else "draw"
    actual_btts = "yes" if int(home) > 0 and int(away) > 0 else "no"
    actual_ou25 = "over_2_5" if total > 2 else "under_2_5"

    eval_conn.execute(
        """
        INSERT INTO actual_results (
            fixture_id, result_status, actual_home_goals, actual_away_goals, actual_score,
            actual_1x2, actual_btts, actual_ou25, finished_at, result_source, score_basis
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fid,
            status,
            int(home),
            int(away),
            scoreline,
            actual_1x2,
            actual_btts,
            actual_ou25,
            (result_row or {}).get("finished_at") or _utc_now(),
            "fixture_results_or_fixtures",
            basis,
        ),
    )
    eval_conn.commit()
    return {
        "synced": True,
        "fixture_id": fid,
        "actual_score": scoreline,
        "actual_1x2": actual_1x2,
        "status": status,
    }
