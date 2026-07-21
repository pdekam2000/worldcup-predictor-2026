"""Odds preparation and timing classification for forward aligned scan."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.gpt_actions.delegation import _fixture_from_db
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot
from worldcup_predictor.odds.freshness_policy import FreshnessStatus
from worldcup_predictor.odds.refresh_gate import ensure_fresh_odds_before_prediction, refresh_live_odds
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.research.ecse_timing_experiment.extract import odds_blob
from worldcup_predictor.research.ecse_timing_experiment.windows import hours_to_kickoff
from worldcup_predictor.research.forward_aligned_scan.constants import TIMING_BUCKETS, TZ_NAME

FRESH_OK = frozenset({FreshnessStatus.FRESH_ODDS.value, "fresh", "ODDS_FRESH", "FRESH_ODDS"})


def _fresh_ok(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, dict):
        for key in ("freshness_flag", "odds_freshness_status", "policy_status", "freshness_class", "freshness_status"):
            if _fresh_ok(v.get(key)):
                return True
        return False
    t = str(v).strip()
    return t in FRESH_OK or ("fresh" in t.lower() and "stale" not in t.lower())


def classify_timing(hours: float | None) -> str:
    if hours is None:
        return "UNKNOWN"
    h = float(hours)
    if h < 0:
        return "STARTED_OR_PAST"
    if h < 1.0:
        return "TOO_LATE_SUB_1H"
    # Prefer more specific late/mid windows when overlapping MATCHDAY
    if 1.0 <= h <= 3.0:
        return "LATE"
    if 3.0 < h <= 12.0:
        return "MID"
    if 12.0 < h <= 24.0:
        return "MATCHDAY"
    if 24.0 < h <= 72.0:
        return "EARLY"
    return "VERY_EARLY"


def prepare_odds(
    fixture: dict[str, Any],
    *,
    prod_conn: Any,
    settings: Settings | None = None,
    as_of: datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Refresh when required and classify odds availability."""
    settings = settings or get_settings()
    now = as_of or datetime.now(timezone.utc)
    fid = int(fixture["fixture_id"])
    kickoff = str(fixture.get("kickoff_utc") or "")
    htk = hours_to_kickoff(kickoff, as_of=now)
    if htk is not None:
        htk = round(htk, 4)
    timing = classify_timing(htk)

    daily = _fixture_from_db(prod_conn, fid)
    if daily is None:
        daily = DailyFixture(
            fixture_id=fid,
            provider_fixture_id=fid,
            competition_key=str(fixture.get("competition_key") or ""),
            home_team=str(fixture.get("home_team") or ""),
            away_team=str(fixture.get("away_team") or ""),
            kickoff_utc=kickoff,
            status=str(fixture.get("status") or "NS"),
            season=None,
        )

    # Never refresh or use odds for already-started fixtures
    status_u = str(fixture.get("status") or getattr(daily, "status", "") or "").upper()
    if status_u in {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "FT", "AET", "PEN"} or timing == "STARTED_OR_PAST" or (
        htk is not None and float(htk) <= 0
    ):
        return {
            "fixture_id": fid,
            "availability": "BLOCKED_FIXTURE_STARTED",
            "odds": {},
            "home": None,
            "draw": None,
            "away": None,
            "bookmaker_count": None,
            "odds_source": None,
            "provider_timestamp": None,
            "odds_age_hours": None,
            "odds_content_hash": None,
            "hours_to_kickoff": htk,
            "timing_class": timing if timing != "UNKNOWN" else "STARTED_OR_PAST",
            "refresh": {"attempted": False, "success": None, "skipped": "fixture_started"},
            "ready": False,
        }

    refresh_meta: dict[str, Any] = {"attempted": False, "success": None, "dry_run": dry_run}
    if not dry_run:
        try:
            refresh_meta["attempted"] = True
            forced = refresh_live_odds(daily, settings=settings)
            refresh_meta["forced_refresh"] = {
                "ok": bool(forced.get("ok") or forced.get("success")),
                "reason": forced.get("reason") or forced.get("status"),
            }
            # Signature: (conn, row, daily, *, settings, refresh_if_needed)
            # Do not pass kickoff_utc as a kwarg — it lives on the fixture row.
            gate_row = {
                "fixture_id": fid,
                "kickoff_utc": kickoff,
                "home_team": fixture.get("home_team") or getattr(daily, "home_team", None),
                "away_team": fixture.get("away_team") or getattr(daily, "away_team", None),
                "competition_key": fixture.get("competition_key") or getattr(daily, "competition_key", None),
                "status": fixture.get("status") or getattr(daily, "status", None),
            }
            gate = ensure_fresh_odds_before_prediction(
                prod_conn,
                gate_row,
                daily,
                settings=settings,
                refresh_if_needed=True,
            )
            refresh_meta["gate"] = {
                "ok": bool(gate.get("ok") or gate.get("allowed") or gate.get("fresh")),
                "status": gate.get("status") or gate.get("freshness_status") or gate.get("reason"),
                "allowed": gate.get("allowed"),
                "final_block_reason": gate.get("final_block_reason"),
            }
            refresh_meta["success"] = bool(refresh_meta["gate"]["ok"] or refresh_meta["forced_refresh"]["ok"])
        except Exception as exc:
            refresh_meta["success"] = False
            refresh_meta["error"] = f"{type(exc).__name__}:{exc}"

    snap = get_latest_valid_1x2_odds_snapshot(prod_conn, fid, kickoff_utc=kickoff)
    odds = odds_blob(snap)
    h, d, a = odds.get("home"), odds.get("draw"), odds.get("away")
    complete = bool(h and d and a and float(h) > 1 and float(d) > 1 and float(a) > 1)
    fresh = _fresh_ok(odds.get("freshness_status")) or _fresh_ok(odds.get("policy_status"))

    if str(fixture.get("status") or "").upper() in {"1H", "HT", "2H", "ET", "BT", "P", "LIVE"}:
        availability = "BLOCKED_FIXTURE_STARTED"
    elif timing == "STARTED_OR_PAST" or (htk is not None and float(htk) <= 0):
        availability = "BLOCKED_FIXTURE_STARTED"
    elif not complete:
        availability = "BLOCKED_INCOMPLETE_ODDS"
    elif refresh_meta.get("error") and not fresh:
        availability = "BLOCKED_PROVIDER_FAILURE"
    elif not fresh:
        availability = "BLOCKED_STALE_ODDS"
    else:
        availability = "READY_FRESH_ODDS"

    age = odds.get("odds_age_minutes")
    age_hours = None
    try:
        if age is not None:
            age_hours = round(float(age) / 60.0, 4)
    except (TypeError, ValueError):
        age_hours = None

    return {
        "fixture_id": fid,
        "availability": availability,
        "odds": odds,
        "home": h,
        "draw": d,
        "away": a,
        "bookmaker_count": odds.get("bookmaker_count"),
        "odds_source": odds.get("provider"),
        "provider_timestamp": odds.get("fetched_at"),
        "odds_age_hours": age_hours,
        "odds_content_hash": odds.get("content_hash"),
        "hours_to_kickoff": htk,
        "timing_class": timing,
        "refresh": refresh_meta,
        "ready": availability == "READY_FRESH_ODDS",
    }
