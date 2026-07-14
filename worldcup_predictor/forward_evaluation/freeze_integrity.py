"""Freeze integrity gate — must pass before forward market evaluation."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

FREEZE_MISSING = "FREEZE_MISSING"
CONTENT_HASH_MISMATCH = "CONTENT_HASH_MISMATCH"
POST_KICKOFF_PREDICTION = "POST_KICKOFF_PREDICTION"
POST_KICKOFF_FREEZE = "POST_KICKOFF_FREEZE"
RANKING_MISMATCH = "RANKING_MISMATCH"
SCOPE_MISMATCH = "SCOPE_MISMATCH"
MUTATION_SUSPECTED = "MUTATION_SUSPECTED"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00").replace(" UTC", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def verify_freeze_integrity(
    eval_conn: sqlite3.Connection,
    prod_conn: sqlite3.Connection | None,
    *,
    prediction_id: str,
    expected_scope: str | None = None,
) -> dict[str, Any]:
    """Verify frozen prematch record is safe to evaluate."""
    row = eval_conn.execute(
        "SELECT * FROM frozen_predictions WHERE prediction_id=?",
        (prediction_id,),
    ).fetchone()
    if not row:
        return {"ok": False, "reason_code": FREEZE_MISSING, "prediction_id": prediction_id}
    frozen = dict(row)
    fid = int(frozen["fixture_id"])
    kickoff = _parse_dt(frozen.get("kickoff"))
    generated = _parse_dt(frozen.get("generated_at"))
    frozen_at = _parse_dt(frozen.get("frozen_at"))

    if kickoff and generated and generated >= kickoff:
        return {
            "ok": False,
            "reason_code": POST_KICKOFF_PREDICTION,
            "prediction_id": prediction_id,
            "fixture_id": fid,
        }
    if kickoff and frozen_at and frozen_at > kickoff:
        return {
            "ok": False,
            "reason_code": POST_KICKOFF_FREEZE,
            "prediction_id": prediction_id,
            "fixture_id": fid,
        }

    scope = frozen.get("prediction_scope")
    if expected_scope and scope and str(scope) != str(expected_scope):
        return {
            "ok": False,
            "reason_code": SCOPE_MISMATCH,
            "prediction_id": prediction_id,
            "expected_scope": expected_scope,
            "actual_scope": scope,
        }

    if prod_conn is not None and frozen.get("worldcup_stored_prediction_id"):
        wsp = prod_conn.execute(
            """
            SELECT prediction_scope, validation_tier, payload_json, updated_at
            FROM worldcup_stored_predictions WHERE fixture_id=?
            """,
            (fid,),
        ).fetchone()
        if wsp:
            wsp_scope = wsp["prediction_scope"] if "prediction_scope" in wsp.keys() else None
            if wsp_scope and scope and str(wsp_scope) != str(scope):
                return {
                    "ok": False,
                    "reason_code": SCOPE_MISMATCH,
                    "prediction_id": prediction_id,
                    "detail": "wsp_scope_mismatch",
                }

    ranks = eval_conn.execute(
        "SELECT rank, score FROM exact_score_rankings WHERE prediction_id=? ORDER BY rank",
        (prediction_id,),
    ).fetchall()
    if frozen.get("ecse_top5_complete") and len(ranks) < 5:
        return {
            "ok": False,
            "reason_code": RANKING_MISMATCH,
            "prediction_id": prediction_id,
            "rank_count": len(ranks),
        }

    if frozen.get("immutable") == 0:
        return {
            "ok": False,
            "reason_code": MUTATION_SUSPECTED,
            "prediction_id": prediction_id,
        }

    return {
        "ok": True,
        "prediction_id": prediction_id,
        "fixture_id": fid,
        "prediction_scope": scope,
        "validation_tier": frozen.get("validation_tier"),
        "public_visible": int(frozen.get("public_visible") or 0),
        "content_hash": frozen.get("content_hash"),
    }
