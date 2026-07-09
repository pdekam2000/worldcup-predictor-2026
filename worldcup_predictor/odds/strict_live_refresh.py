"""Strict live odds refresh for stale fixtures.

This module intentionally bypasses all local/disk/SQLite odds caches when a
freshness gate has already classified a fixture as stale or missing. A refresh
is only persisted when API-Football returns a real live response with usable
odds. Old cached odds are never re-stamped as fresh.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.backtesting.phase31e_backfill import normalize_odds_bookmakers
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner.euro_c_odds_import import (
    is_fake_odds_payload,
    normalize_uefa_odds_snapshot,
)
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.owner_daily.odds_import import (
    _build_daily_storage_payload,
    _probabilities_valid,
)

RAW_DIR = Path("artifacts/daily_owner/raw_odds_payloads")


def refresh_fixture_odds_live(
    fixture: DailyFixture,
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Force a live API-Football odds call and persist only genuine live data."""
    settings = settings or get_settings()
    fid = int(fixture.provider_fixture_id)

    if not settings.api_football_configured:
        return {
            "fixture_id": fid,
            "status": "api_football_not_configured",
            "live_call_made": False,
            "imported": False,
        }

    api = ApiFootballClient(settings)
    odds_result = api.get_odds(fid, force_refresh=True)

    if odds_result.source != "live":
        return {
            "fixture_id": fid,
            "status": "live_refresh_failed",
            "source": odds_result.source,
            "error": odds_result.error,
            "live_call_made": True,
            "imported": False,
        }

    if not odds_result.ok or is_fake_odds_payload(odds_result.data, source=odds_result.source):
        return {
            "fixture_id": fid,
            "status": "live_odds_empty_or_invalid",
            "source": odds_result.source,
            "error": odds_result.error,
            "live_call_made": True,
            "imported": False,
        }

    bookmakers = normalize_odds_bookmakers(odds_result.data)
    if not bookmakers:
        return {
            "fixture_id": fid,
            "status": "live_odds_no_bookmakers",
            "source": odds_result.source,
            "live_call_made": True,
            "imported": False,
        }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"{fid}_{stamp}_api-football-live.json"
    raw_path.write_text(
        json.dumps(
            {
                "fixture_id": fid,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": "live",
                "data": odds_result.data,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    normalized = normalize_uefa_odds_snapshot(
        bookmakers,
        fixture_id=fid,
        raw_odds_path=str(raw_path),
    )
    if not _probabilities_valid(normalized):
        return {
            "fixture_id": fid,
            "status": "live_odds_invalid_probabilities",
            "source": odds_result.source,
            "live_call_made": True,
            "imported": False,
        }

    payload = _build_daily_storage_payload(
        bookmakers=bookmakers,
        normalized=normalized,
        provider="api-football",
        provider_fixture_id=fid,
        api_source="live",
        raw_path=str(raw_path),
        freshness="fresh",
    )
    payload["strict_live_refresh"] = True
    payload["cache_bypassed"] = True

    if dry_run:
        return {
            "fixture_id": fid,
            "status": "dry_run_live_odds_valid",
            "source": "live",
            "bookmaker_count": normalized.bookmaker_count,
            "live_call_made": True,
            "imported": False,
        }

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    repo.save_snapshot(
        "odds_snapshots",
        fixture_id=fid,
        competition_key=fixture.competition_key,
        payload=payload,
        snapshot_at=payload.get("snapshot_at"),
    )

    return {
        "fixture_id": fid,
        "status": "imported_live",
        "source": "live",
        "snapshot_at": payload.get("snapshot_at"),
        "bookmaker_count": normalized.bookmaker_count,
        "live_call_made": True,
        "imported": True,
    }
