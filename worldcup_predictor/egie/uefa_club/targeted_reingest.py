"""Phase API-J — targeted UEFA re-ingest for recoverable fixtures only."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.uefa_club.config import UEFA_FULL_INCLUDES
from worldcup_predictor.egie.uefa_club.feature_extractors import parse_match_result, parse_uefa_goal_events
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

logger = logging.getLogger(__name__)


def targeted_reingest_uefa(
    fixtures: list[dict[str, Any]],
    fixture_ids: list[int],
    *,
    settings: Settings | None = None,
    max_api_calls: int = 30,
) -> dict[str, Any]:
    settings = settings or get_settings()
    provider = SportmonksProvider(settings)
    fx_by_id = {int(f["sportmonks_fixture_id"]): f for f in fixtures if f.get("sportmonks_fixture_id")}
    api_calls = 0
    recovered_events = 0
    recovered_xg = 0
    unchanged = 0
    errors: list[str] = []
    results: list[dict[str, Any]] = []

    for sm_id in fixture_ids:
        if api_calls >= max_api_calls:
            break
        fx = fx_by_id.get(int(sm_id), {"sportmonks_fixture_id": sm_id})
        cache_file = cache_path(settings, sm_id)
        before = load_cache(cache_file)
        before_payload = (before or {}).get("payload")
        before_goals = len(parse_uefa_goal_events(before_payload))
        home = str(fx.get("home_team") or "")
        away = str(fx.get("away_team") or "")

        st, payload, error = provider.safe_get(
            f"/fixtures/{sm_id}",
            params={"include": UEFA_FULL_INCLUDES},
        )
        api_calls += 1
        if error or not isinstance(payload, dict) or not payload.get("data"):
            errors.append(f"{sm_id}:{error or 'no_data'}"[:120])
            continue

        cached = {
            "sportmonks_fixture_id": sm_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "status_code": st,
            "payload": payload,
            "reingest": "phase_api_j_targeted",
        }
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cached, indent=2, default=str), encoding="utf-8")

        after_goals = len(parse_uefa_goal_events(payload))
        from worldcup_predictor.egie.uefa_club.feature_extractors import parse_uefa_xg

        after_xg = parse_uefa_xg(payload).get("home_xg") is not None
        if after_goals > before_goals:
            recovered_events += 1
        elif after_goals == before_goals:
            unchanged += 1
        if after_xg:
            recovered_xg += 1
        result = parse_match_result(payload, home_team=home, away_team=away)
        results.append(
            {
                "fixture_id": sm_id,
                "events_before": before_goals,
                "events_after": after_goals,
                "first_goal_side": result.get("first_goal_team_side"),
                "home_xg": parse_uefa_xg(payload).get("home_xg"),
            }
        )

    return {
        "targeted_fixture_ids": fixture_ids[:max_api_calls],
        "api_calls_used": api_calls,
        "recovered_events": recovered_events,
        "recovered_xg": recovered_xg,
        "unchanged": unchanged,
        "errors_sample": errors[:10],
        "per_fixture": results,
    }


def expand_uefa_fixture_mapping(
    existing: dict[str, Any],
    *,
    settings: Settings | None = None,
    season_ids: tuple[int, ...] = (23619, 23620, 23616, 21638, 21639),
    per_season_limit: int = 30,
    max_api_calls: int = 40,
) -> dict[str, Any]:
    """Merge season-filtered finished fixtures into mapping (cache-first expansion)."""
    settings = settings or get_settings()
    provider = SportmonksProvider(settings)
    api_calls = 0
    seen = {int(f["sportmonks_fixture_id"]) for f in existing.get("fixtures") or [] if f.get("sportmonks_fixture_id")}
    new_fixtures: list[dict[str, Any]] = list(existing.get("fixtures") or [])
    league_by_id = {2: "champions_league", 5: "europa_league", 2286: "conference_league", 1326: "uefa_super_cup"}

    for sid in season_ids:
        if api_calls >= max_api_calls:
            break
        st, pl, _ = provider.safe_get(
            "/fixtures",
            params={"filters": f"fixtureSeasons:{sid}", "include": "participants;state;scores", "per_page": 50},
        )
        api_calls += 1
        rows = (pl or {}).get("data") or []
        added = 0
        for row in rows:
            if added >= per_season_limit:
                break
            if int(row.get("state_id") or 0) not in (5, 7, 8):
                continue
            sm_id = int(row.get("id") or 0)
            if sm_id <= 0 or sm_id in seen:
                continue
            home = away = ""
            home_id = away_id = None
            for p in row.get("participants") or []:
                loc = str((p.get("meta") or {}).get("location") or "").lower()
                if loc == "home":
                    home, home_id = str(p.get("name") or ""), p.get("id")
                elif loc == "away":
                    away, away_id = str(p.get("name") or ""), p.get("id")
            lid = int(row.get("league_id") or 0)
            new_fixtures.append(
                {
                    "sportmonks_fixture_id": sm_id,
                    "fixture_id": sm_id,
                    "competition_key": league_by_id.get(lid, "champions_league"),
                    "league_id": lid,
                    "season_id": row.get("season_id"),
                    "kickoff_utc": row.get("starting_at"),
                    "home_team": home,
                    "away_team": away,
                    "home_team_id": home_id,
                    "away_team_id": away_id,
                    "state_id": row.get("state_id"),
                    "fixture_name": row.get("name"),
                    "mapping_status": "sportmonks_mapped_api_j",
                }
            )
            seen.add(sm_id)
            added += 1

    by_league: dict[str, int] = {}
    for f in new_fixtures:
        ck = str(f.get("competition_key") or "unknown")
        by_league[ck] = by_league.get(ck, 0) + 1

    return {
        **existing,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_calls_made": int(existing.get("api_calls_made") or 0) + api_calls,
        "fixture_count": len(new_fixtures),
        "by_competition_key": by_league,
        "fixtures": new_fixtures,
        "expansion_note": "Phase API-J season-filtered merge",
    }
