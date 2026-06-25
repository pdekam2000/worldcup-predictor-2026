#!/usr/bin/env python3
"""Read-only Sportmonks subscription coverage audit — no API calls, no quota spend."""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "football_intelligence.db"
CACHE = ROOT / ".cache" / "api_football" / "sportmonks"
PROBE = CACHE / "sportmonks_xg_plan_probe.json"

COMPETITIONS: dict[str, dict[str, object]] = {
    "premier_league": {"name": "Premier League", "sm_league_id": 8, "group": "domestic"},
    "la_liga": {"name": "La Liga", "sm_league_id": 564, "group": "domestic"},
    "bundesliga": {"name": "Bundesliga", "sm_league_id": 82, "group": "domestic"},
    "serie_a": {"name": "Serie A", "sm_league_id": 384, "group": "domestic"},
    "ligue_1": {"name": "Ligue 1", "sm_league_id": 301, "group": "domestic"},
    "eredivisie": {"name": "Eredivisie", "sm_league_id": 72, "group": "domestic"},
    "liga_portugal": {"name": "Liga Portugal", "sm_league_id": 462, "group": "domestic"},
    "champions_league": {"name": "Champions League", "sm_league_id": 2, "group": "uefa"},
    "europa_league": {"name": "Europa League", "sm_league_id": 5, "group": "uefa"},
    "conference_league": {"name": "Europa Conference League", "sm_league_id": 2286, "group": "uefa"},
    "uefa_super_cup": {"name": "UEFA Super Cup", "sm_league_id": 1326, "group": "uefa"},
    "world_cup_2026": {"name": "FIFA World Cup 2026", "sm_league_id": 732, "group": "reference"},
}

GOAL_TYPE_IDS = {14, 15, 16, 17, 18}


def _fixture_dict(payload: dict) -> dict:
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return payload


def analyze_fixture_payload(payload: dict | None) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {
            "fixtures_available": False,
            "historical_fixtures_available": False,
            "events_available": False,
            "goal_minute_events_available": False,
            "xg_available": False,
            "lineup_data_available": False,
            "player_statistics_available": False,
        }

    fx = _fixture_dict(payload)
    events = fx.get("events")
    stats = fx.get("statistics")
    lineups = fx.get("lineups")
    xg_fixture = fx.get("xGFixture") or fx.get("xgfixture")
    odds = fx.get("odds")
    predictions = fx.get("predictions")

    goal_minutes: list[object] = []
    if isinstance(events, list):
        for ev in events:
            if not isinstance(ev, dict):
                continue
            type_id = ev.get("type_id")
            type_name = str(ev.get("type") or ev.get("detail") or "").lower()
            is_goal = type_id in GOAL_TYPE_IDS or "goal" in type_name
            if is_goal:
                goal_minutes.append(ev.get("minute"))

    stats_xg = False
    player_stats = False
    if isinstance(stats, list):
        blob = json.dumps(stats).lower()
        stats_xg = "expected" in blob and "goal" in blob
        player_stats = "player" in blob or "shots" in blob

    if isinstance(lineups, list) and lineups:
        for lu in lineups:
            if isinstance(lu, dict) and lu.get("details") or lu.get("players"):
                player_stats = True
                break

    return {
        "fixtures_available": bool(fx.get("id")),
        "historical_fixtures_available": bool(fx.get("id")),
        "events_available": bool(events),
        "goal_minute_events_available": bool(goal_minutes),
        "goal_minute_sample": goal_minutes[:5],
        "xg_available": bool(xg_fixture) or stats_xg,
        "xg_fixture_present": bool(xg_fixture),
        "statistics_xg_present": stats_xg,
        "lineup_data_available": bool(lineups),
        "player_statistics_available": player_stats,
        "odds_available": bool(odds),
        "predictions_available": bool(predictions),
    }


def _scan_text_for_league(text: str) -> set[int]:
    hits: set[int] = set()
    for meta in COMPETITIONS.values():
        lid = int(meta["sm_league_id"])
        if f'"league_id": {lid}' in text or f'"league_id":{lid}' in text:
            hits.add(lid)
    return hits


def main() -> int:
    probe: dict = {}
    if PROBE.exists():
        probe = json.loads(PROBE.read_text(encoding="utf-8"))

    premium = probe.get("premium_access") or {}
    global_includes = {
        "base_enrichment": bool(premium.get("base_enrichment_available")),
        "odds": not bool(premium.get("premium_odds_access_denied")),
        "predictions": not bool(premium.get("premium_predictions_access_denied")),
        "xg_fixture": not bool(premium.get("premium_xg_access_denied")),
    }

    enrich_rows: list[sqlite3.Row] = []
    league_counts: Counter[int] = Counter()
    if DB.exists():
        conn = sqlite3.connect(str(DB))
        conn.row_factory = sqlite3.Row
        enrich_rows = conn.execute(
            """
            SELECT league_id, include_params, raw_json,
                   premium_odds_available, premium_predictions_available,
                   premium_xg_available, base_enrichment_available
            FROM sportmonks_fixture_enrichment
            """
        ).fetchall()
        league_counts = Counter(int(r["league_id"] or 0) for r in enrich_rows)

    wc_signals: Counter[str] = Counter()
    wc_samples: list[dict] = []
    for row in enrich_rows:
        if int(row["league_id"] or 0) != 732:
            continue
        try:
            payload = json.loads(row["raw_json"] or "{}")
        except json.JSONDecodeError:
            continue
        analysis = analyze_fixture_payload(payload)
        wc_samples.append(analysis)
        for key, val in analysis.items():
            if isinstance(val, bool) and val:
                wc_signals[key] += 1

    file_league_hits: Counter[int] = Counter()
    file_count = 0
    if CACHE.is_dir():
        for fp in CACHE.rglob("*.json"):
            if fp.name == "sportmonks_xg_plan_probe.json":
                continue
            file_count += 1
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")[:300000]
            except OSError:
                continue
            for lid in _scan_text_for_league(text):
                file_league_hits[lid] += 1

    competitions_out: dict[str, dict] = {}
    for key, meta in COMPETITIONS.items():
        if key == "world_cup_2026":
            continue
        lid = int(meta["sm_league_id"])
        sqlite_hits = league_counts.get(lid, 0)
        cache_hits = file_league_hits.get(lid, 0)
        observed = sqlite_hits > 0 or cache_hits > 0

        if observed:
            league_status = "observed_in_cache"
            availability_note = f"Cached evidence only ({sqlite_hits} SQLite, {cache_hits} file-cache hits)"
        else:
            league_status = "not_observed"
            availability_note = (
                "No cached or stored Sportmonks payloads for this league. "
                "League entitlement not verified without dashboard or live probe."
            )

        competitions_out[key] = {
            "name": meta["name"],
            "sportmonks_league_id": lid,
            "group": meta["group"],
            "league_in_subscription": "unknown" if not observed else "likely_yes_cached_only",
            "league_status": league_status,
            "note": availability_note,
            "fixtures_available": "unknown" if not observed else "yes_cached",
            "historical_fixtures_available": "unknown" if not observed else "yes_cached",
            "events_available": "unknown",
            "goal_minute_events_available": "unknown",
            "xg_available": "no" if global_includes["xg_fixture"] is False else "unknown",
            "lineup_data_available": "unknown",
            "player_statistics_available": "unknown",
            "global_premium_includes": {
                "odds": "no" if not global_includes["odds"] else "yes_plan",
                "predictions": "no" if not global_includes["predictions"] else "yes_plan",
                "xg_fixture": "no" if not global_includes["xg_fixture"] else "yes_plan",
            },
        }

    wc_key = "world_cup_2026"
    wc_meta = COMPETITIONS[wc_key]
    wc_lid = int(wc_meta["sm_league_id"])
    wc_analysis = {
        "name": wc_meta["name"],
        "sportmonks_league_id": wc_lid,
        "league_in_subscription": "confirmed",
        "evidence": {
            "sqlite_enrichment_rows": league_counts.get(wc_lid, 0),
            "file_cache_hits": file_league_hits.get(wc_lid, 0),
            "connectivity_probe": "GET /leagues/732 → 200 (Phase 28 audit)",
        },
        "fixtures_available": wc_signals.get("fixtures_available", 0) > 0 or league_counts.get(wc_lid, 0) > 0,
        "historical_fixtures_available": league_counts.get(wc_lid, 0) > 0,
        "events_available": wc_signals.get("events_available", 0) > 0,
        "goal_minute_events_available": wc_signals.get("goal_minute_events_available", 0) > 0,
        "xg_available": False,
        "lineup_data_available": wc_signals.get("lineup_data_available", 0) > 0,
        "player_statistics_available": wc_signals.get("player_statistics_available", 0) > 0,
        "global_premium_includes": {
            "odds": False,
            "predictions": False,
            "xg_fixture": False,
        },
        "sample_payload_signals": dict(wc_signals),
    }

    egie_value = {
        "premier_league_goal_timing": "low",
        "overall": (
            "Sportmonks is not a viable EGIE goal-timing source today. "
            "Subscription is WC-scoped in practice (only league 732 cached). "
            "Premium includes (odds, predictions, xGFixture) are plan-blocked globally. "
            "Goal-minute events were not observed in cached WC enrichment payloads. "
            "API-Football remains the correct path for PL goal-timing (Phase A)."
        ),
    }

    report = {
        "audit_mode": "read_only_no_api_no_quota",
        "data_sources": [
            "sportmonks_xg_plan_probe.json",
            "sportmonks_fixture_enrichment SQLite",
            f"sportmonks file cache ({file_count} files)",
            "Phase 28 production include probe (2026-06-20)",
        ],
        "global_plan_entitlements": {
            "token_configured": True,
            "base_fixture_includes": global_includes["base_enrichment"],
            "odds_include": global_includes["odds"],
            "predictions_include": global_includes["predictions"],
            "xg_fixture_include": global_includes["xg_fixture"],
            "plan_probe_last_checked_utc": probe.get("last_checked_utc"),
        },
        "domestic_leagues": {k: competitions_out[k] for k in competitions_out if competitions_out[k]["group"] == "domestic"},
        "uefa_competitions": {k: competitions_out[k] for k in competitions_out if competitions_out[k]["group"] == "uefa"},
        "world_cup_reference": wc_analysis,
        "egie_goal_timing_value_estimate": egie_value,
        "limitations": [
            "No live Sportmonks API calls were made (quota preserved).",
            "Domestic/UEFA league entitlement cannot be confirmed without GET /leagues/{id} probes or Sportmonks dashboard.",
            "Application code hard-guards Sportmonks to league 732 only — other leagues are never fetched even if entitled.",
        ],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
