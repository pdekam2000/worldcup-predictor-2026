"""Leakage and integrity checks for L2-F historical replay."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any


def _parse(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip().replace(" ", "T").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return None


def assert_prediction_before_kickoff(frozen_at: str | None, kickoff: str | None) -> str | None:
    fr, ko = _parse(frozen_at), _parse(kickoff)
    if fr is None or ko is None:
        return "missing_timestamps"
    if fr >= ko:
        return "frozen_at_not_before_kickoff"
    return None


def assert_result_after_prediction(
    *,
    frozen_at: str | None,
    result_synced_at: str | None,
    kickoff: str | None,
) -> str | None:
    fr = _parse(frozen_at)
    rs = _parse(result_synced_at) or _parse(kickoff)
    if fr is None or rs is None:
        return None  # soft: missing result timestamp not always present
    if rs < fr:
        return "result_timestamp_before_prediction"
    return None


def payload_contains_result_leakage(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    text = json.dumps(payload, default=str).lower()
    banned = (
        "actual_home_goals",
        "actual_away_goals",
        "actual_score",
        "final_score",
        "ft_home_goals",
        "ft_away_goals",
        "result_home",
        "result_away",
    )
    return any(b in text for b in banned)


def check_shadow_payloads_no_results(fi_conn: sqlite3.Connection, fixture_id: int) -> list[str]:
    from worldcup_predictor.research.football_strength_foundation.constants import SHADOW_TABLE

    issues: list[str] = []
    try:
        rows = fi_conn.execute(
            f"SELECT shadow_id, payload_json FROM {SHADOW_TABLE} WHERE fixture_id=?",
            (int(fixture_id),),
        ).fetchall()
    except Exception as exc:
        return [f"shadow_read_error:{type(exc).__name__}"]
    for r in rows:
        sid = r[0]
        raw = r[1]
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        if payload_contains_result_leakage(payload if isinstance(payload, dict) else {"x": payload}):
            issues.append(f"result_leakage_in_payload:{sid}")
    return issues


def freeze_hash_unchanged(eval_conn: sqlite3.Connection, freeze_id: str, expected_hash: str | None) -> str | None:
    if not expected_hash:
        return None
    row = eval_conn.execute(
        "SELECT content_hash, payload_hash, source_payload_hash FROM frozen_predictions WHERE prediction_id=?",
        (freeze_id,),
    ).fetchone()
    if not row:
        return "freeze_missing"
    hashes = [h for h in row if h]
    if expected_hash not in hashes and expected_hash not in (row[0], row[1], row[2]):
        # If freeze has no hash columns populated, skip hard fail
        if not any(hashes):
            return None
        return "freeze_hash_changed"
    return None
