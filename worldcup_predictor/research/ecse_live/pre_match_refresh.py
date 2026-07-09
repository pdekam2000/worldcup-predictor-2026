"""Audited pre-match ECSE snapshot refresh.

ECSE-LIVE-1 stores one current snapshot per fixture. For a controlled prematch
rerun after genuinely fresh odds arrive, an existing *unevaluated* snapshot may
be refreshed in place while preserving its row id. Evaluated snapshots are
never changed. The previous snapshot is written to ecse_live_api_log before the
update so the replacement is auditable.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.ecse_live.store import get_snapshot, has_evaluation


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def refresh_unevaluated_snapshot(
    conn: sqlite3.Connection,
    payload: dict[str, Any],
) -> tuple[int | None, str]:
    """Replace the current pre-match snapshot only when it has no evaluation."""
    fixture_id = int(payload["fixture_id"])
    existing = get_snapshot(conn, fixture_id)
    if not existing:
        return None, "missing_existing_snapshot"

    snapshot_id = int(existing["id"])
    if has_evaluation(conn, snapshot_id):
        return None, "evaluated_snapshot_locked"

    audit_payload = {
        "reason": "fresh_odds_prematch_regeneration",
        "fixture_id": fixture_id,
        "snapshot_id": snapshot_id,
        "previous_snapshot": existing,
        "incoming_generated_at": payload.get("generated_at"),
        "incoming_model_version": payload.get("model_version"),
    }

    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO ecse_live_api_log (
                phase, provider, endpoint, entity_key, action, status, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ECSE-LIVE-1",
                "internal",
                "pre_match_refresh",
                str(fixture_id),
                "archive_before_refresh",
                "ok",
                json.dumps(audit_payload, default=str),
                _utc_now(),
            ),
        )
        conn.execute(
            """
            UPDATE ecse_prediction_snapshots SET
                registry_fixture_id=?, competition_key=?, home_team=?, away_team=?,
                kickoff_utc=?, generated_at=?, model_version=?, lambda_home=?, lambda_away=?,
                top_10_scorelines_json=?, top_1_score=?, top_3_scores_json=?,
                top_5_scores_json=?, confidence_score=?, data_quality_score=?,
                raw_features_json=?, prediction_source=?, is_frozen=1
            WHERE id=? AND fixture_id=?
            """,
            (
                payload.get("registry_fixture_id"),
                payload.get("competition_key"),
                payload.get("home_team"),
                payload.get("away_team"),
                payload.get("kickoff_utc"),
                payload.get("generated_at"),
                payload["model_version"],
                float(payload["lambda_home"]),
                float(payload["lambda_away"]),
                json.dumps(payload["top_10_scorelines"], default=str),
                payload["top_1_score"],
                json.dumps(payload["top_3_scores"], default=str),
                json.dumps(payload["top_5_scores"], default=str),
                float(payload["confidence_score"]),
                float(payload["data_quality_score"]),
                json.dumps(payload.get("raw_features") or {}, default=str),
                payload.get("prediction_source") or "live_odds",
                snapshot_id,
                fixture_id,
            ),
        )
        conn.commit()
        return snapshot_id, "refreshed"
    except Exception:
        conn.rollback()
        raise
