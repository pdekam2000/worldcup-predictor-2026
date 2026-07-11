"""Pre-prediction odds refresh gate — forced live refresh before STALE_ODDS block."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.provider_features.odds_snapshot_parser import (
    NormalizedOddsLine,
    _is_match_winner_market,
    normalize_snapshot_odds_lines,
)
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot
from worldcup_predictor.odds.freshness_metadata import build_fixture_freshness_metadata
from worldcup_predictor.odds.freshness_policy import (
    FreshnessStatus,
    get_allowed_odds_ttl_seconds,
)
from worldcup_predictor.odds.strict_live_refresh import refresh_fixture_odds_live
from worldcup_predictor.owner.euro_c_odds_import import _latest_odds_snapshot, is_fake_odds_payload
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture

MARKET_1X2 = "match_winner"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _sanitize_error(msg: str | None) -> str | None:
    if not msg:
        return None
    text = str(msg)
    for token in ("api_key", "apikey", "authorization", "bearer", "token", "secret"):
        if token in text.lower():
            return "provider_error_redacted"
    return text[:300]


def _median_1x2_decimal(lines: list[NormalizedOddsLine]) -> dict[str, Any]:
    per_bm: dict[str, dict[str, float]] = {}
    for line in lines:
        if not _is_match_winner_market(line.market_name):
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
        return {"valid": False, "bookmaker_count": 0, "home_odds": None, "draw_odds": None, "away_odds": None}
    home_vals = sorted(r["home"] for r in per_bm.values() if "home" in r)
    draw_vals = sorted(r["draw"] for r in per_bm.values() if "draw" in r)
    away_vals = sorted(r["away"] for r in per_bm.values() if "away" in r)
    if not home_vals or not draw_vals or not away_vals:
        return {"valid": False, "bookmaker_count": len(per_bm), "home_odds": None, "draw_odds": None, "away_odds": None}
    return {
        "valid": True,
        "bookmaker_count": len(per_bm),
        "bookmaker": sorted(per_bm.keys())[0],
        "home_odds": home_vals[len(home_vals) // 2],
        "draw_odds": draw_vals[len(draw_vals) // 2],
        "away_odds": away_vals[len(away_vals) // 2],
    }


def validate_legitimate_1x2_snapshot(
    conn: sqlite3.Connection,
    fixture_id: int,
    *,
    kickoff_utc: str | None = None,
) -> tuple[bool, str | None, dict[str, Any]]:
    canonical = get_latest_valid_1x2_odds_snapshot(conn, int(fixture_id), kickoff_utc=kickoff_utc)
    meta = canonical.to_dict()
    if canonical.freshness_class == "ODDS_MISSING":
        return False, "NO_LEGITIMATE_1X2_ODDS", meta
    if canonical.freshness_class == "ODDS_TIMESTAMP_MISSING":
        return False, "ODDS_TIMESTAMP_MISSING", meta
    if canonical.freshness_class == "ODDS_PROVIDER_MISSING":
        return False, "ODDS_PROVIDER_MISSING", meta
    if canonical.freshness_class == "ODDS_MARKET_NOT_SUPPORTED":
        return False, "ODDS_MARKET_NOT_SUPPORTED", meta
    if canonical.freshness_class == "ODDS_INCOMPLETE":
        return False, "NO_LEGITIMATE_1X2_ODDS", meta
    return (
        True,
        None,
        {
            **meta,
            "valid": True,
            "snapshot_at": canonical.fetched_at_utc,
            "home_odds": canonical.home_odds,
            "draw_odds": canonical.draw_odds,
            "away_odds": canonical.away_odds,
            "bookmaker": canonical.bookmaker,
            "provider": canonical.provider,
        },
    )


def _freshness_for_row(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    refresh_attempted: bool = False,
    refresh_success: bool | None = None,
    refresh_reason: str | None = None,
) -> dict[str, Any]:
    return build_fixture_freshness_metadata(
        conn,
        fixture_id=int(row["fixture_id"]),
        kickoff_utc=row.get("kickoff_utc"),
        round_name=row.get("round_name"),
        status=row.get("status"),
        odds_refresh_attempted=refresh_attempted,
        odds_refresh_success=refresh_success,
        odds_refresh_reason=refresh_reason,
    )


def _build_block_diagnostics(
    *,
    row: dict[str, Any],
    freshness: dict[str, Any],
    refresh_result: dict[str, Any] | None,
    final_block_reason: str,
    legitimate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _utc_now_iso()
    kickoff = row.get("kickoff_utc")
    allowed_ttl = get_allowed_odds_ttl_seconds(kickoff)
    snap_at = freshness.get("odds_snapshot_at") or (legitimate or {}).get("snapshot_at") or (legitimate or {}).get("fetched_at_utc")
    age_hours = freshness.get("odds_age_hours")
    odds_age_seconds = round(float(age_hours) * 3600, 1) if age_hours is not None else None
    refresh = refresh_result or {}
    attempts = refresh.get("attempts") or refresh.get("provider_attempts") or []
    provider_errors = [
        {
            "provider": a.get("provider"),
            "reason": _sanitize_error(str(a.get("reason") or a.get("error") or "")),
        }
        for a in attempts
        if isinstance(a, dict)
    ]
    return {
        "fixture_id": int(row["fixture_id"]),
        "match": f"{row.get('home_team')} vs {row.get('away_team')}",
        "competition": row.get("competition_key"),
        "kickoff_utc": kickoff,
        "current_time_utc": now,
        "last_odds_fetched_at_utc": snap_at,
        "odds_age_seconds": odds_age_seconds,
        "allowed_ttl_seconds": allowed_ttl,
        "freshness_status": freshness.get("odds_freshness_status"),
        "freshness_reason": freshness.get("explanation") or final_block_reason,
        "refresh_attempted": bool(refresh.get("refresh_attempted")),
        "refresh_success": refresh.get("refresh_success"),
        "provider_used": refresh.get("provider") or refresh.get("selected_provider"),
        "providers_attempted": refresh.get("providers_tried") or [a.get("provider") for a in attempts],
        "provider_errors": provider_errors,
        "final_block_reason": final_block_reason,
        "market": MARKET_1X2,
        "bookmaker": (legitimate or {}).get("bookmaker"),
        "home_odds": (legitimate or {}).get("home_odds"),
        "draw_odds": (legitimate or {}).get("draw_odds"),
        "canonical_snapshot_source": (legitimate or {}).get("canonical_snapshot_source") or CANONICAL_SOURCE,
        "timestamp_source_field": (legitimate or {}).get("timestamp_source_field") or freshness.get("timestamp_source_field"),
        "provider_request_success": refresh.get("provider_request_success"),
        "refresh_imported_rows": refresh.get("refresh_imported_rows"),
        "refresh_complete_1x2_rows": refresh.get("refresh_complete_1x2_rows"),
        "refresh_persisted": refresh.get("refresh_persisted"),
        "odds_age_minutes": round(float(age_hours) * 60, 1) if age_hours is not None else (legitimate or {}).get("odds_age_minutes"),
        "freshness_class": freshness.get("odds_freshness_class") or (legitimate or {}).get("freshness_class"),
        "away_odds": (legitimate or {}).get("away_odds"),
    }


CANONICAL_SOURCE = "odds_snapshots"

_AFTER_REFRESH_BLOCK = {
    "ODDS_STALE": "STALE_ODDS_AFTER_REFRESH",
    "ODDS_TIMESTAMP_MISSING": "ODDS_TIMESTAMP_MISSING_AFTER_REFRESH",
    "ODDS_PROVIDER_MISSING": "ODDS_PROVIDER_MISSING_AFTER_REFRESH",
    "ODDS_MARKET_NOT_SUPPORTED": "ODDS_MARKET_NOT_SUPPORTED_AFTER_REFRESH",
    "ODDS_INCOMPLETE": "ODDS_INCOMPLETE_AFTER_REFRESH",
}


def _after_refresh_block_reason(freshness: dict[str, Any], legit_reason: str | None) -> str:
    fc = freshness.get("odds_freshness_class")
    if fc in _AFTER_REFRESH_BLOCK:
        return _AFTER_REFRESH_BLOCK[fc]
    if legit_reason:
        return f"{legit_reason}_AFTER_REFRESH"
    return "STALE_ODDS_AFTER_REFRESH"


def refresh_live_odds(fixture: DailyFixture, *, settings: Settings | None = None) -> dict[str, Any]:
    """Attempt multi-provider live 1X2 refresh; never re-stamps stale cache as fresh."""
    settings = settings or get_settings()
    result = refresh_fixture_odds_live(fixture, settings=settings, dry_run=False)
    attempts = result.get("attempts") or []
    return {
        "success": bool(result.get("imported")),
        "provider_request_success": bool(result.get("imported")),
        "refresh_attempted": True,
        "refresh_success": bool(result.get("imported")),
        "refresh_imported_rows": 1 if result.get("imported") else 0,
        "refresh_complete_1x2_rows": 1 if result.get("imported") else 0,
        "refresh_persisted": bool(result.get("imported")),
        "provider": result.get("provider") or result.get("selected_live_provider"),
        "providers_tried": result.get("providers_tried") or [a.get("provider") for a in attempts],
        "attempts": attempts,
        "fetched_at_utc": result.get("snapshot_at"),
        "status": result.get("status"),
        "market_quality": result.get("market_quality"),
        "live_calls": result.get("live_calls"),
    }


def ensure_fresh_odds_before_prediction(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    daily: DailyFixture,
    *,
    settings: Settings | None = None,
    refresh_if_needed: bool = True,
) -> dict[str, Any]:
    """
    Gate predictions on fresh valid 1X2 odds.
    Attempts forced live refresh when stale/missing before blocking.
    """
    settings = settings or get_settings()
    freshness = _freshness_for_row(conn, row)
    cls_status = freshness.get("odds_freshness_status")
    refresh_result: dict[str, Any] | None = None

    legit_ok, legit_reason, legit_meta = validate_legitimate_1x2_snapshot(
        conn, int(row["fixture_id"]), kickoff_utc=row.get("kickoff_utc")
    )
    pre_refresh_legit_ok = legit_ok
    pre_refresh_legit_reason = legit_reason
    needs_refresh = (
        freshness.get("requires_fresh_odds")
        or not legit_ok
        or cls_status
        in (
            FreshnessStatus.STALE_ODDS.value,
            FreshnessStatus.ODDS_MISSING.value,
            FreshnessStatus.ODDS_FRESHNESS_UNKNOWN.value,
        )
    )

    if not needs_refresh and legit_ok:
        return {
            "allowed": True,
            "final_block_reason": None,
            "refresh_attempted": False,
            "refresh_success": None,
            "freshness": freshness,
            "diagnostics": None,
        }

    if refresh_if_needed:
        refresh_result = refresh_live_odds(daily, settings=settings)
        freshness = _freshness_for_row(
            conn,
            row,
            refresh_attempted=True,
            refresh_success=refresh_result.get("refresh_success"),
            refresh_reason=str(refresh_result.get("status") or ""),
        )
        legit_ok, legit_reason, legit_meta = validate_legitimate_1x2_snapshot(
            conn, int(row["fixture_id"]), kickoff_utc=row.get("kickoff_utc")
        )

    if not refresh_if_needed or not refresh_result:
        reason = legit_reason or "STALE_ODDS"
        if cls_status == FreshnessStatus.STALE_ODDS.value:
            reason = "STALE_ODDS"
        return {
            "allowed": False,
            "final_block_reason": reason,
            "refresh_attempted": False,
            "refresh_success": False,
            "freshness": freshness,
            "diagnostics": _build_block_diagnostics(
                row=row,
                freshness=freshness,
                refresh_result=None,
                final_block_reason=reason,
                legitimate=legit_meta,
            ),
        }

    if not refresh_result.get("success"):
        if not pre_refresh_legit_ok and pre_refresh_legit_reason in {
            "NO_LEGITIMATE_1X2_ODDS",
            "ODDS_TIMESTAMP_MISSING",
        }:
            reason = "NO_LEGITIMATE_1X2_ODDS_AFTER_REFRESH"
        else:
            reason = "STALE_ODDS_REFRESH_FAILED"
        if not settings.api_football_configured and not settings.sportmonks_configured:
            reason = "ODDS_PROVIDER_UNAVAILABLE"
        return {
            "allowed": False,
            "final_block_reason": reason,
            "refresh_attempted": True,
            "refresh_success": False,
            "freshness": freshness,
            "diagnostics": _build_block_diagnostics(
                row=row,
                freshness=freshness,
                refresh_result=refresh_result,
                final_block_reason=reason,
                legitimate=legit_meta,
            ),
        }

    if freshness.get("requires_fresh_odds"):
        reason = _after_refresh_block_reason(freshness, legit_reason)
        return {
            "allowed": False,
            "final_block_reason": reason,
            "refresh_attempted": True,
            "refresh_success": True,
            "freshness": freshness,
            "diagnostics": _build_block_diagnostics(
                row=row,
                freshness=freshness,
                refresh_result=refresh_result,
                final_block_reason=reason,
                legitimate=legit_meta,
            ),
        }

    if not legit_ok:
        reason = _after_refresh_block_reason(freshness, legit_reason or "NO_LEGITIMATE_1X2_ODDS")
        return {
            "allowed": False,
            "final_block_reason": reason,
            "refresh_attempted": True,
            "refresh_success": True,
            "freshness": freshness,
            "diagnostics": _build_block_diagnostics(
                row=row,
                freshness=freshness,
                refresh_result=refresh_result,
                final_block_reason=reason,
                legitimate=legit_meta,
            ),
        }

    return {
        "allowed": True,
        "final_block_reason": None,
        "refresh_attempted": True,
        "refresh_success": True,
        "freshness": freshness,
        "diagnostics": None,
    }
