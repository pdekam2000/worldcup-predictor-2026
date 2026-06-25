"""Sportmonks PL fixture lookup — backfill scope only (league 8)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.cache.api_cache import ApiCache
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.providers.sportmonks_fixture_lookup import (
    LOOKUP_INCLUDES,
    team_names_match,
)

PREMIER_LEAGUE_SPORTMONKS_LEAGUE_ID = 8
DATE_CACHE_ENDPOINT = "fixtures/date"
LOOKUP_SUCCESS_TTL_SECONDS = 7 * 24 * 3600
DATE_LIST_TTL_SECONDS = 24 * 3600


def _lookup_cache(settings: Settings) -> ApiCache:
    cache_dir = Path(settings.api_cache_dir) / "sportmonks"
    return ApiCache(cache_dir, default_ttl_seconds=LOOKUP_SUCCESS_TTL_SECONDS)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    raw = str(value).replace("Z", "+00:00")
    try:
        if "T" in raw:
            return datetime.fromisoformat(raw).date()
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _participant_side(participant: dict[str, Any]) -> str:
    meta = participant.get("meta") or {}
    return str(meta.get("location") or "").lower()


def _fixture_participants(item: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in (item.get("participants") or []) if isinstance(p, dict)]


def _is_pl_fixture(item: dict[str, Any]) -> bool:
    try:
        return int(item.get("league_id") or 0) == PREMIER_LEAGUE_SPORTMONKS_LEAGUE_ID
    except (TypeError, ValueError):
        return False


def _match_fixture_item(
    item: dict[str, Any],
    *,
    home_team: str,
    away_team: str,
) -> bool:
    if not _is_pl_fixture(item):
        return False
    participants = _fixture_participants(item)
    if len(participants) < 2:
        name_blob = str(item.get("name") or "").lower()
        return team_names_match(home_team, name_blob) and team_names_match(away_team, name_blob)

    home_name = away_name = None
    for participant in participants:
        side = _participant_side(participant)
        pname = str(participant.get("name") or "")
        if side == "home":
            home_name = pname
        elif side == "away":
            away_name = pname
    if home_name and away_name:
        return team_names_match(home_team, home_name) and team_names_match(away_team, away_name)

    names = {str(p.get("name") or "") for p in participants}
    home_ok = any(team_names_match(home_team, n) for n in names)
    away_ok = any(team_names_match(away_team, n) for n in names)
    return home_ok and away_ok


def _include_string() -> str:
    return ";".join(LOOKUP_INCLUDES)


def _fetch_fixtures_for_date(
    provider: SportmonksProvider,
    cache: ApiCache,
    *,
    day: date,
    league_id: int = PREMIER_LEAGUE_SPORTMONKS_LEAGUE_ID,
) -> tuple[list[dict[str, Any]], int | None, str | None]:
    date_str = day.isoformat()
    cache_params = {"date": date_str, "league_id": league_id}
    cached = cache.get(DATE_CACHE_ENDPOINT, cache_params)
    if isinstance(cached, dict) and isinstance(cached.get("items"), list):
        return cached["items"], 200, None

    endpoint = f"/fixtures/date/{date_str}"
    status, payload, error = provider.safe_get(
        endpoint,
        params={
            "include": _include_string(),
            "filters": f"fixtureLeagues:{league_id}",
            "per_page": 50,
        },
    )
    if error:
        return [], status, error

    data = payload.get("data") if isinstance(payload, dict) else None
    items = [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
    cache.set(
        DATE_CACHE_ENDPOINT,
        cache_params,
        {"items": items},
        ttl_seconds=DATE_LIST_TTL_SECONDS,
    )
    return items, status, None


def lookup_premier_league_fixture(
    *,
    api_fixture_id: int,
    home_team: str,
    away_team: str,
    kickoff_date: str | None,
    settings: Settings | None = None,
) -> tuple[int | None, str, int]:
    """
    Resolve Sportmonks fixture id for a PL match.

    Returns (sportmonks_fixture_id, source, api_calls_made).
  """
    settings = settings or get_settings()
    provider = SportmonksProvider(settings)
    if not provider.is_configured:
        return None, "not_configured", 0

    cache = _lookup_cache(settings)
    kickoff = _parse_date(kickoff_date)
    if kickoff is None:
        return None, "no_kickoff_date", 0

    api_calls = 0
    for offset in (0, -1, 1):
        day = kickoff + timedelta(days=offset)
        items, status, error = _fetch_fixtures_for_date(provider, cache, day=day)
        if error and status not in (None, 200):
            continue
        if items and offset == 0 and status == 200:
            api_calls += 1

        for item in items:
            if not _match_fixture_item(item, home_team=home_team, away_team=away_team):
                continue
            try:
                sm_id = int(item.get("id") or 0)
            except (TypeError, ValueError):
                continue
            if sm_id > 0:
                cache.set(
                    "fixture_lookup",
                    {"api_fixture_id": api_fixture_id, "league_id": PREMIER_LEAGUE_SPORTMONKS_LEAGUE_ID},
                    {"sportmonks_fixture_id": sm_id, "item": item},
                    ttl_seconds=LOOKUP_SUCCESS_TTL_SECONDS,
                )
                return sm_id, "live_lookup" if api_calls else "cache_lookup", api_calls

    return None, "not_found", api_calls
