#!/usr/bin/env python3
"""Live Sportmonks xG/Pressure access probe — minimal quota, read-only."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

COMPONENTS: dict[str, dict[str, Any]] = {
    "xG Match": {
        "includes": "participants;scores;xGFixture.type;lineups.xGLineup.type",
        "keys": ("xGFixture", "xgfixture"),
    },
    "Pressure Index": {
        "includes": "participants;pressure",
        "keys": ("pressure",),
    },
    "Match Centre": {
        "includes": "participants;scores;state;events.type;statistics;lineups",
        "keys": ("participants", "scores", "events", "statistics"),
    },
    "Lineup": {
        "includes": "participants;lineups.player;lineups.details.type;formations",
        "keys": ("lineups",),
    },
    "Team Recent Form": {
        "includes": "participants;form",
        "keys": ("form",),
    },
    "Odds": {
        "includes": "participants;odds.bookmaker;odds.market",
        "keys": ("odds",),
    },
    "Prediction Model": {
        "includes": "participants;predictions.type",
        "keys": ("predictions",),
    },
}


def _sqlite_wc_fixtures(limit: int = 1) -> list[dict[str, Any]]:
    import sqlite3

    db_path = ROOT / "data" / "football_intelligence.db"
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT sportmonks_fixture_id, fixture_id_api_football, league_id "
        "FROM sportmonks_fixture_enrichment WHERE league_id=732 LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [
        {
            "label": "world_cup_732_stored",
            "sportmonks_fixture_id": int(r["sportmonks_fixture_id"]),
            "api_fixture_id": r["fixture_id_api_football"],
            "league_id": 732,
            "mapping_source": "sqlite_enrichment",
        }
        for r in rows
    ]


def _discover_league_fixture(
    provider: SportmonksProvider,
    league_id: int,
    label: str,
) -> dict[str, Any] | None:
    status, payload, _error = provider.safe_get(
        "/fixtures",
        params={"filters": f"fixtureLeagues:{league_id}", "per_page": 1, "include": "participants"},
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if status != 200 or not isinstance(data, list) or not data:
        return None
    item = data[0]
    try:
        sm_id = int(item.get("id") or 0)
    except (TypeError, ValueError):
        return None
    if sm_id <= 0:
        return None
    return {
        "label": label,
        "sportmonks_fixture_id": sm_id,
        "api_fixture_id": None,
        "league_id": league_id,
        "mapping_source": f"live_discovery_league_{league_id}",
        "fixture_name": item.get("name"),
    }


def _load_fixtures(provider: SportmonksProvider) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    # World Cup — stored id (may fail if plan excludes WC)
    out.extend(_sqlite_wc_fixtures(limit=1))

    # Champions League — discover live
    cl = _discover_league_fixture(provider, 2, "champions_league_2")
    if cl:
        out.append(cl)

    # Premier League — only if mapped in SQLite
    import sqlite3

    db_path = ROOT / "data" / "football_intelligence.db"
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        pl = conn.execute(
            "SELECT sportmonks_fixture_id, fixture_id_api_football "
            "FROM sportmonks_fixture_enrichment WHERE league_id=8 LIMIT 1"
        ).fetchone()
        conn.close()
        if pl:
            out.append(
                {
                    "label": "premier_league_8_mapped",
                    "sportmonks_fixture_id": int(pl["sportmonks_fixture_id"]),
                    "api_fixture_id": pl["fixture_id_api_football"],
                    "league_id": 8,
                    "mapping_source": "sqlite_enrichment",
                }
            )

    return out[:5]


def _top_keys(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict):
        return sorted(data.keys())[:25]
    return sorted(payload.keys())[:15]


def _has_keys(payload: Any, keys: tuple[str, ...]) -> bool:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        for k in keys:
            if k in data:
                return True
    blob = json.dumps(payload, default=str).lower()
    return any(k.lower() in blob for k in keys)


def _diagnose(status: int | None, payload: Any, error: str | None, has_data: bool) -> str:
    if status == 403:
        return "subscription_or_include_not_entitled"
    if status == 404:
        return "endpoint_or_include_not_found"
    if isinstance(payload, dict):
        msg = str(payload.get("message") or "")
        if "don't have access" in msg.lower() or "no result" in msg.lower():
            return "league_or_fixture_not_in_subscription_scope"
    if status == 200 and not has_data:
        return "empty_response_check_mapping_or_plan"
    if status == 200 and has_data:
        return "access_ok"
    if error:
        return "request_error"
    return "unknown"


def probe() -> dict[str, Any]:
    settings = get_settings()
    provider = SportmonksProvider(settings)
    fixtures = _load_fixtures(provider)

    results: list[dict[str, Any]] = []
    api_calls = 0
    subscription_meta: Any = None

    for fx in fixtures:
        sm_id = int(fx["sportmonks_fixture_id"])
        for component, spec in COMPONENTS.items():
            endpoint = f"/fixtures/{sm_id}"
            includes = spec["includes"]
            status, payload, error = provider.safe_get(endpoint, params={"include": includes})
            api_calls += 1
            if subscription_meta is None and isinstance(payload, dict) and payload.get("subscription"):
                subscription_meta = payload.get("subscription")

            has_target = _has_keys(payload, tuple(spec["keys"]))
            has_data_obj = isinstance((payload or {}).get("data"), dict)
            message = (payload or {}).get("message") if isinstance(payload, dict) else None

            entry: dict[str, Any] = {
                "fixture_label": fx["label"],
                "sportmonks_fixture_id": sm_id,
                "api_fixture_id": fx.get("api_fixture_id"),
                "league_id": fx.get("league_id"),
                "mapping_source": fx.get("mapping_source"),
                "fixture_name": fx.get("fixture_name"),
                "component": component,
                "endpoint": endpoint,
                "include_param": includes,
                "status_code": status,
                "response_has_data_object": has_data_obj,
                "response_has_target_data": has_target,
                "response_top_keys": _top_keys(payload),
                "api_message": message,
                "error_redacted": error,
                "likely_cause": _diagnose(status, payload, error, has_target),
            }
            if status == 403:
                entry["access_denied_hint"] = str(error or message or "HTTP 403")[:300]
            results.append(entry)

    return {
        "probed_at_utc": datetime.now(timezone.utc).isoformat(),
        "token_configured": settings.sportmonks_configured,
        "token_source": "SPORTMONKS_API_TOKEN or SPORTMONKS_API_KEY from .env via get_settings()",
        "base_url": settings.sportmonks_base_url,
        "subscription_from_response": subscription_meta,
        "fixtures_tested": fixtures,
        "api_calls_made": api_calls,
        "tests": results,
    }


def main() -> int:
    report = probe()
    out_path = ROOT / "artifacts" / "sportmonks_xg_pressure_access_probe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    sub = report.get("subscription_from_response")
    plans = sub[0].get("plans") if isinstance(sub, list) and sub else (sub or {}).get("plans") if isinstance(sub, dict) else None
    print(json.dumps(
        {
            "artifact": str(out_path),
            "api_calls": report["api_calls_made"],
            "fixtures": report["fixtures_tested"],
            "plan": plans,
            "summary": [
                {
                    "fixture": t["fixture_label"],
                    "component": t["component"],
                    "status": t["status_code"],
                    "has_data": t["response_has_target_data"],
                    "cause": t["likely_cause"],
                }
                for t in report["tests"]
            ],
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
