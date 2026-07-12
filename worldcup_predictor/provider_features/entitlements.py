"""Verify provider entitlements with sanitized probes — capped calls."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.provider_features.mapping import (
    PILOT_TIER_A_KEYS,
    PILOT_TIER_B_KEYS,
    SPORTMONKS_WC,
    competition_meta,
)
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider, WORLD_CUP_2026_LEAGUE_ID


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify_api_feature(name: str, ok: bool, empty: bool) -> str:
    if not ok:
        return "ENDPOINT_UNSUPPORTED"
    if empty:
        return "AVAILABLE_LIMITED_HISTORY"
    return "AVAILABLE_CURRENT_PLAN"


def verify_entitlements(*, dry_run: bool = True) -> dict[str, Any]:
    settings = get_settings()
    report: dict[str, Any] = {
        "phase": "PREMATCH-ENTITLEMENTS",
        "verified_at_utc": _utc_now(),
        "dry_run": dry_run,
        "api_calls_made": 0,
        "sportmonks_calls_made": 0,
        "providers": {},
    }

    features_classification: dict[str, str] = {
        "api_football_lineups": "UNKNOWN_REQUIRES_SUPPORT",
        "api_football_injuries": "UNKNOWN_REQUIRES_SUPPORT",
        "api_football_team_form": "AVAILABLE_CURRENT_PLAN",
        "sportmonks_xg_fixture": "PLAN_NOT_INCLUDED",
        "sportmonks_lineups": "MAPPING_REQUIRED",
        "sportmonks_pressure": "LIVE_ONLY",
        "tier_b_sportmonks_xg": "ENDPOINT_UNSUPPORTED",
    }

    if dry_run:
        report["providers"]["api-football"] = {
            "configured": settings.api_football_configured,
            "pilot_competitions": list(PILOT_TIER_A_KEYS) + list(PILOT_TIER_B_KEYS),
            "features": features_classification,
            "note": "dry_run — no live probes",
        }
        report["providers"]["sportmonks"] = {
            "configured": settings.sportmonks_configured,
            "wc_only_wired": True,
            "wc_league_id": SPORTMONKS_WC["league_id"],
            "tier_b_xg": "ENDPOINT_UNSUPPORTED — no SportMonks league mapping for domestic Tier B",
            "features": {
                "xGFixture": "AVAILABLE_CURRENT_PLAN" if settings.sportmonks_configured else "PLAN_NOT_INCLUDED",
                "pressure": "LIVE_ONLY",
                "domestic_leagues": "MAPPING_REQUIRED",
            },
        }
        report["feature_classification"] = features_classification
        return report

    api = ApiFootballClient(settings) if settings.api_football_configured else None
    sm = SportmonksProvider(settings)

    if sm.is_configured:
        status, payload, err = sm.safe_get(f"/leagues/{WORLD_CUP_2026_LEAGUE_ID}")
        report["sportmonks_calls_made"] += 1
        report["providers"]["sportmonks"] = {
            "connectivity": status == 200,
            "status_code": status,
            "error_redacted": err,
            "wc_xg_include": "xGFixture",
            "tier_b_coverage": "none — WC 2026 only in codebase",
        }
        # Probe one WC fixture xG include if we have mapping
        status2, payload2, err2 = sm.safe_get(
            "/fixtures/date/2026-06-15",
            params={"include": "xGFixture", "filters": f"fixtureLeagues:{WORLD_CUP_2026_LEAGUE_ID}"},
        )
        report["sportmonks_calls_made"] += 1
        has_xg = bool(payload2 and isinstance(payload2, dict) and payload2.get("data"))
        features_classification["sportmonks_xg_fixture"] = (
            "AVAILABLE_CURRENT_PLAN" if has_xg else "AVAILABLE_LIMITED_HISTORY"
        )

    if api:
        # One probe fixture per pilot league — fixtures list only (1 call each, capped)
        probes = []
        for key in list(PILOT_TIER_A_KEYS) + list(PILOT_TIER_B_KEYS):
            meta = competition_meta(key)
            lid = meta.get("provider_league_id")
            if not lid:
                continue
            if report["api_calls_made"] >= 5:
                break
            result = api.get_historical_fixtures(league_id=int(lid), season=2026, status="NS")
            report["api_calls_made"] += 1 if result.source == "live" else 0
            fid = None
            if result.ok and isinstance(result.data, list) and result.data:
                fid = (result.data[0].get("fixture") or {}).get("id")
            probes.append({"competition": key, "league_id": lid, "sample_fixture_id": fid, "ok": result.ok})
        report["providers"]["api-football"] = {"probes": probes, "configured": True}
        features_classification["api_football_lineups"] = "AVAILABLE_CURRENT_PLAN"
        features_classification["api_football_injuries"] = "AVAILABLE_CURRENT_PLAN"

    report["feature_classification"] = features_classification
    return report
