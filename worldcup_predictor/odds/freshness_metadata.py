"""Attach odds freshness metadata to prediction payloads — metadata only."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from worldcup_predictor.odds.freshness_policy import (
    build_prediction_freshness_metadata,
    classify_odds_freshness,
    is_knockout_match,
    is_low_priority_match,
)


def load_fixture_odds_snapshot(conn: sqlite3.Connection, fixture_id: int) -> tuple[str | None, str | None]:
    row = conn.execute(
        "SELECT snapshot_at, payload_json FROM odds_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
        (fixture_id,),
    ).fetchone()
    if not row:
        return None, None
    source = None
    try:
        payload = json.loads(row["payload_json"])
        source = payload.get("source_provider") or payload.get("source")
    except (json.JSONDecodeError, TypeError):
        source = "odds_snapshots"
    return row["snapshot_at"], source


def build_fixture_freshness_metadata(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    kickoff_utc: str | None,
    round_name: str | None,
    status: str | None,
    prediction_generated_at: str | None = None,
    odds_refresh_attempted: bool = False,
    odds_refresh_success: bool | None = None,
    odds_refresh_reason: str | None = None,
) -> dict[str, Any]:
    snap_at, source = load_fixture_odds_snapshot(conn, fixture_id)
    knockout = is_knockout_match(round_name=round_name, status=status)
    low_pri = is_low_priority_match(kickoff_utc=kickoff_utc)
    cls = classify_odds_freshness(
        odds_snapshot_at=snap_at,
        reference_at=prediction_generated_at,
        knockout=knockout,
        low_priority=low_pri,
        odds_source=source,
        has_odds=bool(snap_at),
    )
    return build_prediction_freshness_metadata(
        cls,
        odds_refresh_attempted=odds_refresh_attempted,
        odds_refresh_success=odds_refresh_success,
        odds_refresh_reason=odds_refresh_reason,
    )


def stamp_payload_odds_freshness(payload: dict[str, Any], freshness: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["odds_freshness_metadata"] = freshness
    payload["odds_freshness_status"] = freshness.get("odds_freshness_status")
    payload["odds_age_hours"] = freshness.get("odds_age_hours")
    payload["odds_source"] = freshness.get("odds_source")
    payload["odds_snapshot_at"] = freshness.get("odds_snapshot_at")
    payload["requires_fresh_odds"] = freshness.get("requires_fresh_odds")
    return payload
