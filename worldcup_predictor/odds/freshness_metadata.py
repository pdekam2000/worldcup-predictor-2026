"""Attach odds freshness metadata to prediction payloads — metadata only."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.odds.canonical_snapshot import (
    get_latest_valid_1x2_odds_snapshot,
    policy_status_from_canonical,
)
from worldcup_predictor.odds.freshness_policy import (
    build_prediction_freshness_metadata,
    classify_odds_freshness,
    is_knockout_match,
    is_low_priority_match,
)
from worldcup_predictor.odds.timestamp_normalization import parse_timestamp_utc

MARKET_1X2 = "match_winner"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def load_fixture_odds_snapshot(conn: sqlite3.Connection, fixture_id: int) -> tuple[str | None, str | None]:
    snap = get_latest_valid_1x2_odds_snapshot(conn, int(fixture_id))
    return snap.fetched_at_utc, snap.provider


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
    canonical = get_latest_valid_1x2_odds_snapshot(
        conn,
        int(fixture_id),
        kickoff_utc=kickoff_utc,
        now_utc=parse_timestamp_utc(prediction_generated_at) if prediction_generated_at else None,
    )
    snap_at = canonical.fetched_at_utc
    source = canonical.provider
    has_odds = canonical.bookmaker_count > 0 and canonical.freshness_class not in {
        "ODDS_MISSING",
        "ODDS_MARKET_NOT_SUPPORTED",
    }
    knockout = is_knockout_match(round_name=round_name, status=status)
    low_pri = is_low_priority_match(kickoff_utc=kickoff_utc)
    cls = classify_odds_freshness(
        odds_snapshot_at=snap_at,
        reference_at=prediction_generated_at,
        kickoff_utc=kickoff_utc,
        knockout=knockout,
        low_priority=low_pri,
        odds_source=source,
        has_odds=has_odds,
    )
    out = build_prediction_freshness_metadata(
        cls,
        odds_refresh_attempted=odds_refresh_attempted,
        odds_refresh_success=odds_refresh_success,
        odds_refresh_reason=odds_refresh_reason,
    )
    out["canonical_odds_snapshot"] = canonical.to_dict()
    out["odds_freshness_class"] = canonical.freshness_class
    out["odds_freshness_reason"] = canonical.freshness_reason
    out["timestamp_source_field"] = canonical.timestamp_source_field
    if canonical.odds_age_minutes is not None:
        out["odds_age_hours"] = round(canonical.odds_age_minutes / 60.0, 2)
    out["odds_snapshot_at"] = snap_at
    out["odds_freshness_status"] = policy_status_from_canonical(canonical)
    out["freshness_flag"] = out["odds_freshness_status"]
    out["requires_fresh_odds"] = canonical.freshness_class in {
        "ODDS_STALE",
        "ODDS_TIMESTAMP_MISSING",
        "ODDS_PROVIDER_MISSING",
        "ODDS_INCOMPLETE",
    } or cls.requires_fresh_odds
    return out


def stamp_payload_odds_freshness(payload: dict[str, Any], freshness: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["odds_freshness_metadata"] = freshness
    payload["odds_freshness_status"] = freshness.get("odds_freshness_status")
    payload["odds_age_hours"] = freshness.get("odds_age_hours")
    payload["odds_source"] = freshness.get("odds_source")
    payload["odds_snapshot_at"] = freshness.get("odds_snapshot_at")
    payload["requires_fresh_odds"] = freshness.get("requires_fresh_odds")
    return payload


def enrich_snapshot_payload_metadata(
    payload: dict[str, Any],
    *,
    fixture_id: int,
    kickoff_utc: str | None,
    provider: str,
    bookmaker: str | None,
    home_odds: float | None,
    draw_odds: float | None,
    away_odds: float | None,
    freshness_status: str,
    freshness_reason: str | None = None,
    raw_payload: Any = None,
) -> dict[str, Any]:
    """Attach canonical odds snapshot metadata fields."""
    out = dict(payload)
    fetched = out.get("snapshot_at") or _utc_now_iso()
    out["snapshot_at"] = fetched
    out.update(
        {
            "fixture_id": fixture_id,
            "provider": provider,
            "bookmaker": bookmaker,
            "market": MARKET_1X2,
            "home_odds": home_odds,
            "draw_odds": draw_odds,
            "away_odds": away_odds,
            "fetched_at_utc": fetched,
            "kickoff_utc": kickoff_utc,
            "freshness_status": freshness_status,
            "freshness_reason": freshness_reason,
        }
    )
    age_hours = classify_odds_freshness(
        odds_snapshot_at=fetched,
        kickoff_utc=kickoff_utc,
        has_odds=True,
    ).odds_age_hours
    if age_hours is not None:
        out["odds_age_seconds"] = round(age_hours * 3600, 1)
    if raw_payload is not None:
        try:
            blob = json.dumps(raw_payload, sort_keys=True, default=str)
            out["source_payload_hash"] = hashlib.sha256(blob.encode()).hexdigest()[:16]
        except (TypeError, ValueError):
            pass
    return out
