"""Cache-first controlled odds lookup for owner Tier B scope."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.egie.provider_features.odds_snapshot_parser import (
    NormalizedOddsLine,
    _is_match_winner_market,
    normalize_snapshot_odds_lines,
)
from worldcup_predictor.gpt_actions.competition_normalize import normalize_competition_key
from worldcup_predictor.gpt_actions.tier_b_shadow_registry import get_tier_b_domain
from worldcup_predictor.owner.euro_c_odds_import import _latest_odds_snapshot, is_fake_odds_payload
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.odds.freshness_metadata import build_fixture_freshness_metadata
from worldcup_predictor.odds.refresh_gate import refresh_live_odds, validate_legitimate_1x2_snapshot
from worldcup_predictor.odds.freshness_policy import FreshnessStatus

MAX_TIER_B_PROVIDER_CALLS_PER_REQUEST = 5
_PREMATCH_WINDOW_HOURS = 48.0


def _median_decimal_odds(lines: list[NormalizedOddsLine]) -> dict[str, float | None]:
    per_bm: dict[str, dict[str, float]] = {}
    for line in lines:
        if not _is_match_winner_market(line.market_name):
            continue
        key = line.selection.lower().strip()
        if key not in {"home", "draw", "away"}:
            continue
        per_bm.setdefault(line.bookmaker, {})[key] = float(line.odd)
    if not per_bm:
        return {"home": None, "draw": None, "away": None, "bookmaker_count": 0}
    out: dict[str, float | None] = {}
    for side in ("home", "draw", "away"):
        vals = sorted(r[side] for r in per_bm.values() if side in r)
        out[side] = vals[len(vals) // 2] if vals else None
    return {**out, "bookmaker_count": len(per_bm)}


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _within_operational_window(kickoff_utc: str | None) -> bool:
    ko = _parse_kickoff(kickoff_utc)
    if not ko:
        return False
    now = datetime.now(timezone.utc)
    hours = (ko - now).total_seconds() / 3600.0
    return -6.0 <= hours <= _PREMATCH_WINDOW_HOURS


def _odds_from_snapshot(conn, fixture_id: int) -> dict[str, Any]:
    snap = _latest_odds_snapshot(conn, int(fixture_id))
    if not snap:
        return {"home": None, "draw": None, "away": None, "bookmaker_count": 0, "cache_hit": False}
    payload = snap.get("payload")
    source = None
    if isinstance(payload, dict):
        source = str(payload.get("provider") or payload.get("source") or "")
    if is_fake_odds_payload(payload, source=source):
        return {"home": None, "draw": None, "away": None, "bookmaker_count": 0, "cache_hit": False}
    lines = normalize_snapshot_odds_lines(payload, fixture_id=int(fixture_id))
    decimals = _median_decimal_odds(lines)
    return {
        **decimals,
        "cache_hit": decimals.get("bookmaker_count", 0) > 0,
        "odds_timestamp": snap.get("snapshot_at"),
        "freshness_status": snap.get("freshness") or "cached",
    }


class OwnerOddsBudget:
    def __init__(self, max_calls: int = MAX_TIER_B_PROVIDER_CALLS_PER_REQUEST) -> None:
        self.max_calls = max_calls
        self.provider_calls = 0

    def can_call_provider(self) -> bool:
        return self.provider_calls < self.max_calls


def controlled_owner_odds_lookup(
    fixture: DailyFixture,
    *,
    tier: str,
    settings: Settings | None = None,
    budget: OwnerOddsBudget | None = None,
    allow_provider: bool = True,
) -> dict[str, Any]:
    """Cache-first odds for owner scope; controlled provider fetch for Tier B only."""
    settings = settings or get_settings()
    budget = budget or OwnerOddsBudget()
    conn = connect(settings.sqlite_path)
    fid = int(fixture.fixture_id)
    canon = normalize_competition_key(fixture.competition_key) or fixture.competition_key

    record: dict[str, Any] = {
        "fixture_id": fid,
        "competition": canon,
        "tier": tier,
        "cache_hit": False,
        "provider_called": False,
        "odds_found": False,
        "bookmaker_count": 0,
        "odds_timestamp": None,
        "freshness_status": "missing",
        "failure_reason": None,
    }

    try:
        cached = _odds_from_snapshot(conn, fid)
        record["cache_hit"] = bool(cached.get("cache_hit"))
        meta = build_fixture_freshness_metadata(
            conn,
            fixture_id=fid,
            kickoff_utc=fixture.kickoff_utc,
            round_name=None,
            status=fixture.status,
        )
        record["freshness_status"] = meta.get("odds_freshness_status") or "missing"
        if cached.get("bookmaker_count", 0) > 0:
            record.update(
                {
                    "odds_found": True,
                    "bookmaker_count": cached.get("bookmaker_count"),
                    "odds_timestamp": cached.get("odds_timestamp"),
                    "home": cached.get("home"),
                    "draw": cached.get("draw"),
                    "away": cached.get("away"),
                }
            )
        legit_ok, legit_reason, _ = validate_legitimate_1x2_snapshot(conn, fid)
        if (
            legit_ok
            and meta.get("odds_freshness_status") == FreshnessStatus.FRESH_ODDS.value
            and not meta.get("requires_fresh_odds")
        ):
            record["freshness_status"] = FreshnessStatus.FRESH_ODDS.value
            return record

        if tier != "B":
            if not record["odds_found"]:
                record["failure_reason"] = "no_cached_odds"
            elif not legit_ok:
                record["failure_reason"] = legit_reason or "no_legitimate_odds"
            elif meta.get("requires_fresh_odds"):
                record["failure_reason"] = "odds_freshness_invalid"
            return record

        domain = get_tier_b_domain(canon) if canon else None
        if not domain:
            record["failure_reason"] = "not_approved_tier_b"
            return record

        if not _within_operational_window(fixture.kickoff_utc):
            record["failure_reason"] = "outside_operational_window"
            return record

        if not allow_provider or not budget.can_call_provider():
            record["failure_reason"] = "provider_budget_exhausted_or_disabled"
            return record

        budget.provider_calls += 1
        record["provider_called"] = True
        refresh = refresh_live_odds(fixture, settings=settings)
        record["refresh_attempted"] = True
        record["refresh_success"] = bool(refresh.get("success"))
        record["import_status"] = refresh.get("status")
        if refresh.get("provider"):
            record["provider_used"] = refresh.get("provider")

        after = _odds_from_snapshot(conn, fid)
        meta_after = build_fixture_freshness_metadata(
            conn,
            fixture_id=fid,
            kickoff_utc=fixture.kickoff_utc,
            round_name=None,
            status=fixture.status,
            odds_refresh_attempted=True,
            odds_refresh_success=record["refresh_success"],
            odds_refresh_reason=str(refresh.get("status") or ""),
        )
        legit_ok, legit_reason, _ = validate_legitimate_1x2_snapshot(conn, fid)
        if after.get("bookmaker_count", 0) > 0 and legit_ok and not meta_after.get("requires_fresh_odds"):
            record.update(
                {
                    "odds_found": True,
                    "cache_hit": record["cache_hit"] or bool(after.get("cache_hit")),
                    "bookmaker_count": after.get("bookmaker_count"),
                    "odds_timestamp": after.get("odds_timestamp"),
                    "freshness_status": FreshnessStatus.FRESH_ODDS.value,
                    "home": after.get("home"),
                    "draw": after.get("draw"),
                    "away": after.get("away"),
                }
            )
        else:
            if not refresh.get("success"):
                record["failure_reason"] = "STALE_ODDS_REFRESH_FAILED"
            elif meta_after.get("requires_fresh_odds"):
                record["failure_reason"] = "STALE_ODDS_AFTER_REFRESH"
            else:
                record["failure_reason"] = legit_reason or "NO_LEGITIMATE_1X2_ODDS_AFTER_REFRESH"
    finally:
        conn.close()

    return record
