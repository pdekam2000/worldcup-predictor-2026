"""STEP 2 — UEFA fixture mapping from Sportmonks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.uefa_club.config import LEAGUE_ID_TO_KEY, UEFA_CLUB_LEAGUES
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

_FINISHED_STATE_IDS = {5, 7, 8}


def _teams(item: dict[str, Any]) -> tuple[str, str, int | None, int | None]:
    home = away = ""
    home_id = away_id = None
    for p in item.get("participants") or []:
        if not isinstance(p, dict):
            continue
        loc = str((p.get("meta") or {}).get("location") or "").lower()
        name = str(p.get("name") or "")
        pid = p.get("id")
        if loc == "home":
            home, home_id = name, int(pid) if pid else None
        elif loc == "away":
            away, away_id = name, int(pid) if pid else None
    return home, away, home_id, away_id


def build_uefa_fixture_mapping(
    *,
    settings: Settings | None = None,
    max_pages_per_league: int = 5,
    per_page: int = 50,
    finished_only: bool = True,
    limit_per_league: int | None = 80,
) -> dict[str, Any]:
    settings = settings or get_settings()
    provider = SportmonksProvider(settings)
    api_calls = 0
    fixtures: list[dict[str, Any]] = []

    for league in UEFA_CLUB_LEAGUES:
        league_count = 0
        for page in range(1, max_pages_per_league + 1):
            if limit_per_league and league_count >= limit_per_league:
                break
            st, payload, _err = provider.safe_get(
                "/fixtures",
                params={
                    "filters": f"fixtureLeagues:{league.sportmonks_league_id}",
                    "include": "participants;state;scores",
                    "per_page": per_page,
                    "page": page,
                },
            )
            api_calls += 1
            data = (payload or {}).get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list) or not data:
                break
            for row in data:
                if not isinstance(row, dict):
                    continue
                state_id = int(row.get("state_id") or 0)
                if finished_only and state_id not in _FINISHED_STATE_IDS:
                    continue
                sm_id = int(row.get("id") or 0)
                if sm_id <= 0:
                    continue
                home, away, home_id, away_id = _teams(row)
                fixtures.append(
                    {
                        "sportmonks_fixture_id": sm_id,
                        "fixture_id": sm_id,
                        "competition_key": league.key,
                        "league_id": league.sportmonks_league_id,
                        "league_name": league.name,
                        "season_id": row.get("season_id"),
                        "kickoff_utc": row.get("starting_at"),
                        "home_team": home,
                        "away_team": away,
                        "home_team_id": home_id,
                        "away_team_id": away_id,
                        "state_id": state_id,
                        "fixture_name": row.get("name"),
                        "mapping_status": "sportmonks_mapped",
                    }
                )
                league_count += 1
                if limit_per_league and league_count >= limit_per_league:
                    break
            if len(data) < per_page:
                break

    by_league: dict[str, int] = {}
    for f in fixtures:
        ck = str(f.get("competition_key") or "unknown")
        by_league[ck] = by_league.get(ck, 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_calls_made": api_calls,
        "fixture_count": len(fixtures),
        "by_competition_key": by_league,
        "fixtures": fixtures,
    }
