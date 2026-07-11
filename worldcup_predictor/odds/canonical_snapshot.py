"""Canonical latest valid 1X2 odds snapshot bridge — single read path for filter + prediction."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from worldcup_predictor.egie.provider_features.odds_snapshot_parser import (
    NormalizedOddsLine,
    _is_match_winner_market,
    normalize_snapshot_odds_lines,
)
from worldcup_predictor.odds.freshness_policy import (
    FreshnessStatus,
    classify_odds_freshness,
    get_allowed_odds_ttl_seconds,
)
from worldcup_predictor.odds.timestamp_normalization import format_timestamp_utc, parse_timestamp_utc
from worldcup_predictor.owner.euro_c_odds_import import is_fake_odds_payload

MARKET_FULL_TIME_1X2 = "FULL_TIME_1X2"
CANONICAL_SOURCE = "odds_snapshots"

_FRESHNESS_ALIASES = {
    "fetched_at_utc",
    "fetched_at",
    "fetched_utc",
    "last_odds_fetched_at",
    "last_odds_fetched_at_utc",
    "snapshot_at",
    "provider_timestamp",
    "imported_at",
}

_REJECT_MARKET_HINTS = (
    "first half",
    "second half",
    "1st half",
    "2nd half",
    "double chance",
    "draw no bet",
    "qualification",
    "to qualify",
    "extra time",
    "penalty",
    "correct score",
    "half time",
    "ht result",
)

_FT_1X2_ALIASES = {
    "match winner",
    "1x2",
    "full time result",
    "ft result",
    "home draw away",
    "home/draw/away",
    "match result",
    "result",
    "winner",
    "ft_result",
}


def normalize_odds_market_name(value: str | None) -> str | None:
    if not value:
        return None
    n = str(value).lower().strip().replace("_", " ").replace("-", " ")
    if any(hint in n for hint in _REJECT_MARKET_HINTS):
        return None
    compact = n.replace(" ", "")
    if compact in {"1x2", "homedrawaway"}:
        return MARKET_FULL_TIME_1X2
    if n in _FT_1X2_ALIASES or n.replace("/", " ") in _FT_1X2_ALIASES:
        return MARKET_FULL_TIME_1X2
    if _is_match_winner_market(value):
        return MARKET_FULL_TIME_1X2
    return None


def extract_odds_fetched_at_utc(snapshot: dict[str, Any]) -> tuple[datetime | None, str | None, str | None]:
    """Return (aware UTC datetime, canonical iso string, source field name)."""
    column_at = snapshot.get("snapshot_at")
    payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else {}

    candidates: list[tuple[str, Any]] = []
    if column_at:
        candidates.append(("snapshot_at_column", column_at))
    for key in _FRESHNESS_ALIASES:
        if key in payload and payload.get(key):
            candidates.append((f"payload.{key}", payload.get(key)))
    if payload.get("created_at"):
        candidates.append(("payload.created_at", payload.get("created_at")))

    for source_field, raw in candidates:
        parsed = parse_timestamp_utc(raw)
        if parsed is not None:
            return parsed, format_timestamp_utc(parsed), source_field
    return None, None, None


def _median_1x2(lines: list[NormalizedOddsLine]) -> dict[str, Any]:
    per_bm: dict[str, dict[str, float]] = {}
    for line in lines:
        if normalize_odds_market_name(line.market_name) != MARKET_FULL_TIME_1X2:
            continue
        key = line.selection.lower().strip()
        if key not in {"home", "draw", "away"}:
            continue
        try:
            odd = float(line.odd)
        except (TypeError, ValueError):
            continue
        if odd <= 1.0:
            continue
        per_bm.setdefault(line.bookmaker, {})[key] = odd
    if not per_bm:
        return {"valid": False, "bookmaker_count": 0}
    home_vals = sorted(r["home"] for r in per_bm.values() if "home" in r)
    draw_vals = sorted(r["draw"] for r in per_bm.values() if "draw" in r)
    away_vals = sorted(r["away"] for r in per_bm.values() if "away" in r)
    if not home_vals or not draw_vals or not away_vals:
        return {"valid": False, "bookmaker_count": len(per_bm), "incomplete": True}
    return {
        "valid": True,
        "bookmaker_count": len(per_bm),
        "bookmaker": sorted(per_bm.keys())[0],
        "home_odds": home_vals[len(home_vals) // 2],
        "draw_odds": draw_vals[len(draw_vals) // 2],
        "away_odds": away_vals[len(away_vals) // 2],
    }


def _load_snapshot_rows(conn: sqlite3.Connection, fixture_id: int, *, limit: int = 12) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, snapshot_at, payload_json, competition_key
        FROM odds_snapshots
        WHERE fixture_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(fixture_id), int(limit)),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            payload = {}
        out.append(
            {
                "id": int(row["id"]),
                "snapshot_at": row["snapshot_at"],
                "competition_key": row["competition_key"],
                "payload": payload,
            }
        )
    return out


FreshnessClass = Literal[
    "ODDS_MISSING",
    "ODDS_TIMESTAMP_MISSING",
    "ODDS_PROVIDER_MISSING",
    "ODDS_MARKET_NOT_SUPPORTED",
    "ODDS_INCOMPLETE",
    "ODDS_STALE",
    "ODDS_FRESH",
]


@dataclass
class CanonicalOddsSnapshot:
    fixture_id: int
    row_id: int | None
    canonical_snapshot_source: str
    freshness_class: FreshnessClass
    freshness_reason: str
    provider: str | None
    bookmaker: str | None
    bookmaker_count: int
    normalized_market: str | None
    raw_market: str | None
    home_odds: float | None
    draw_odds: float | None
    away_odds: float | None
    fetched_at_utc: str | None
    timestamp_source_field: str | None
    kickoff_utc: str | None = None
    odds_age_seconds: float | None = None
    odds_age_minutes: float | None = None
    allowed_ttl_seconds: int | None = None
    policy_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "row_id": self.row_id,
            "canonical_snapshot_source": self.canonical_snapshot_source,
            "freshness_class": self.freshness_class,
            "freshness_reason": self.freshness_reason,
            "provider": self.provider,
            "bookmaker": self.bookmaker,
            "bookmaker_count": self.bookmaker_count,
            "normalized_market": self.normalized_market,
            "raw_market": self.raw_market,
            "home_odds": self.home_odds,
            "draw_odds": self.draw_odds,
            "away_odds": self.away_odds,
            "fetched_at_utc": self.fetched_at_utc,
            "timestamp_source_field": self.timestamp_source_field,
            "kickoff_utc": self.kickoff_utc,
            "odds_age_seconds": self.odds_age_seconds,
            "odds_age_minutes": self.odds_age_minutes,
            "allowed_ttl_seconds": self.allowed_ttl_seconds,
            "policy_status": self.policy_status,
        }


def _classify_row(
    *,
    fixture_id: int,
    row: dict[str, Any],
    kickoff_utc: str | None,
    now_utc: datetime,
) -> CanonicalOddsSnapshot | None:
    payload = row.get("payload") or {}
    provider = str(payload.get("provider") or payload.get("source") or "") or None
    if is_fake_odds_payload(payload, source=provider):
        return None

    lines = normalize_snapshot_odds_lines(payload, fixture_id=int(fixture_id))
    ft_lines = [ln for ln in lines if normalize_odds_market_name(ln.market_name) == MARKET_FULL_TIME_1X2]
    if not lines:
        return CanonicalOddsSnapshot(
            fixture_id=fixture_id,
            row_id=int(row["id"]),
            canonical_snapshot_source=CANONICAL_SOURCE,
            freshness_class="ODDS_MISSING",
            freshness_reason="no_odds_lines_in_payload",
            provider=provider,
            bookmaker=None,
            bookmaker_count=0,
            normalized_market=None,
            raw_market=None,
            home_odds=None,
            draw_odds=None,
            away_odds=None,
            fetched_at_utc=None,
            timestamp_source_field=None,
            kickoff_utc=kickoff_utc,
        )
    if not ft_lines:
        raw_market = lines[0].market_name if lines else None
        return CanonicalOddsSnapshot(
            fixture_id=fixture_id,
            row_id=int(row["id"]),
            canonical_snapshot_source=CANONICAL_SOURCE,
            freshness_class="ODDS_MARKET_NOT_SUPPORTED",
            freshness_reason="no_full_time_1x2_market",
            provider=provider,
            bookmaker=None,
            bookmaker_count=0,
            normalized_market=None,
            raw_market=raw_market,
            home_odds=None,
            draw_odds=None,
            away_odds=None,
            fetched_at_utc=None,
            timestamp_source_field=None,
            kickoff_utc=kickoff_utc,
        )

    odds = _median_1x2(ft_lines)
    if not odds.get("valid"):
        return CanonicalOddsSnapshot(
            fixture_id=fixture_id,
            row_id=int(row["id"]),
            canonical_snapshot_source=CANONICAL_SOURCE,
            freshness_class="ODDS_INCOMPLETE",
            freshness_reason="incomplete_home_draw_away",
            provider=provider,
            bookmaker=None,
            bookmaker_count=int(odds.get("bookmaker_count") or 0),
            normalized_market=MARKET_FULL_TIME_1X2,
            raw_market=ft_lines[0].market_name,
            home_odds=None,
            draw_odds=None,
            away_odds=None,
            fetched_at_utc=None,
            timestamp_source_field=None,
            kickoff_utc=kickoff_utc,
        )

    fetched_dt, fetched_iso, ts_field = extract_odds_fetched_at_utc(row)
    if fetched_dt is None or fetched_iso is None:
        return CanonicalOddsSnapshot(
            fixture_id=fixture_id,
            row_id=int(row["id"]),
            canonical_snapshot_source=CANONICAL_SOURCE,
            freshness_class="ODDS_TIMESTAMP_MISSING",
            freshness_reason="complete_odds_without_timestamp",
            provider=provider,
            bookmaker=odds.get("bookmaker"),
            bookmaker_count=int(odds.get("bookmaker_count") or 0),
            normalized_market=MARKET_FULL_TIME_1X2,
            raw_market=ft_lines[0].market_name,
            home_odds=odds.get("home_odds"),
            draw_odds=odds.get("draw_odds"),
            away_odds=odds.get("away_odds"),
            fetched_at_utc=None,
            timestamp_source_field=None,
            kickoff_utc=kickoff_utc,
        )

    if not provider:
        return CanonicalOddsSnapshot(
            fixture_id=fixture_id,
            row_id=int(row["id"]),
            canonical_snapshot_source=CANONICAL_SOURCE,
            freshness_class="ODDS_PROVIDER_MISSING",
            freshness_reason="timestamp_present_provider_missing",
            provider=None,
            bookmaker=odds.get("bookmaker"),
            bookmaker_count=int(odds.get("bookmaker_count") or 0),
            normalized_market=MARKET_FULL_TIME_1X2,
            raw_market=ft_lines[0].market_name,
            home_odds=odds.get("home_odds"),
            draw_odds=odds.get("draw_odds"),
            away_odds=odds.get("away_odds"),
            fetched_at_utc=fetched_iso,
            timestamp_source_field=ts_field,
            kickoff_utc=kickoff_utc,
        )

    allowed_ttl = get_allowed_odds_ttl_seconds(kickoff_utc, now_utc)
    age_seconds = max(0.0, (now_utc - fetched_dt).total_seconds())
    age_minutes = round(age_seconds / 60.0, 1)

    if allowed_ttl is None:
        freshness_class: FreshnessClass = "ODDS_STALE"
        policy = FreshnessStatus.STALE_ODDS.value
        reason = "post_kickoff_odds_invalid"
    else:
        policy_cls = classify_odds_freshness(
            odds_snapshot_at=fetched_iso,
            reference_at=now_utc,
            kickoff_utc=kickoff_utc,
            odds_source=provider,
            has_odds=True,
        )
        policy = policy_cls.status.value
        if policy_cls.status == FreshnessStatus.FRESH_ODDS:
            freshness_class = "ODDS_FRESH"
            reason = "within_dynamic_ttl"
        else:
            freshness_class = "ODDS_STALE"
            reason = "exceeds_dynamic_ttl"

    return CanonicalOddsSnapshot(
        fixture_id=fixture_id,
        row_id=int(row["id"]),
        canonical_snapshot_source=CANONICAL_SOURCE,
        freshness_class=freshness_class,
        freshness_reason=reason,
        provider=provider,
        bookmaker=odds.get("bookmaker"),
        bookmaker_count=int(odds.get("bookmaker_count") or 0),
        normalized_market=MARKET_FULL_TIME_1X2,
        raw_market=ft_lines[0].market_name,
        home_odds=odds.get("home_odds"),
        draw_odds=odds.get("draw_odds"),
        away_odds=odds.get("away_odds"),
        fetched_at_utc=fetched_iso,
        timestamp_source_field=ts_field,
        kickoff_utc=kickoff_utc,
        odds_age_seconds=round(age_seconds, 1),
        odds_age_minutes=age_minutes,
        allowed_ttl_seconds=allowed_ttl,
        policy_status=policy,
    )


def get_latest_valid_1x2_odds_snapshot(
    conn: sqlite3.Connection,
    fixture_id: int,
    *,
    kickoff_utc: str | None = None,
    now_utc: datetime | None = None,
) -> CanonicalOddsSnapshot:
    fid = int(fixture_id)
    ref = now_utc or datetime.now(timezone.utc)
    rows = _load_snapshot_rows(conn, fid)
    if not rows:
        return CanonicalOddsSnapshot(
            fixture_id=fid,
            row_id=None,
            canonical_snapshot_source=CANONICAL_SOURCE,
            freshness_class="ODDS_MISSING",
            freshness_reason="no_snapshot_rows",
            provider=None,
            bookmaker=None,
            bookmaker_count=0,
            normalized_market=None,
            raw_market=None,
            home_odds=None,
            draw_odds=None,
            away_odds=None,
            fetched_at_utc=None,
            timestamp_source_field=None,
            kickoff_utc=kickoff_utc,
        )

    best_valid: CanonicalOddsSnapshot | None = None
    first_diagnostic: CanonicalOddsSnapshot | None = None
    for row in rows:
        classified = _classify_row(fixture_id=fid, row=row, kickoff_utc=kickoff_utc, now_utc=ref)
        if classified is None:
            continue
        if first_diagnostic is None:
            first_diagnostic = classified
        if classified.freshness_class in {"ODDS_FRESH", "ODDS_STALE"}:
            best_valid = classified
            break
        if classified.freshness_class in {
            "ODDS_TIMESTAMP_MISSING",
            "ODDS_PROVIDER_MISSING",
            "ODDS_INCOMPLETE",
            "ODDS_MARKET_NOT_SUPPORTED",
        } and best_valid is None:
            best_valid = classified

    if best_valid is not None:
        return best_valid
    return first_diagnostic or CanonicalOddsSnapshot(
        fixture_id=fid,
        row_id=None,
        canonical_snapshot_source=CANONICAL_SOURCE,
        freshness_class="ODDS_MISSING",
        freshness_reason="no_parseable_snapshot",
        provider=None,
        bookmaker=None,
        bookmaker_count=0,
        normalized_market=None,
        raw_market=None,
        home_odds=None,
        draw_odds=None,
        away_odds=None,
        fetched_at_utc=None,
        timestamp_source_field=None,
        kickoff_utc=kickoff_utc,
    )


def policy_status_from_canonical(snap: CanonicalOddsSnapshot) -> str:
    if snap.policy_status:
        return snap.policy_status
    mapping = {
        "ODDS_FRESH": FreshnessStatus.FRESH_ODDS.value,
        "ODDS_STALE": FreshnessStatus.STALE_ODDS.value,
        "ODDS_MISSING": FreshnessStatus.ODDS_MISSING.value,
        "ODDS_TIMESTAMP_MISSING": FreshnessStatus.ODDS_FRESHNESS_UNKNOWN.value,
        "ODDS_PROVIDER_MISSING": FreshnessStatus.ODDS_FRESHNESS_UNKNOWN.value,
        "ODDS_MARKET_NOT_SUPPORTED": FreshnessStatus.ODDS_MISSING.value,
        "ODDS_INCOMPLETE": FreshnessStatus.ODDS_MISSING.value,
    }
    return mapping.get(snap.freshness_class, FreshnessStatus.ODDS_FRESHNESS_UNKNOWN.value)
