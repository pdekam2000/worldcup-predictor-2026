"""Sportmonks World Cup fixture lookup — date + league filter, cache-first."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from worldcup_predictor.cache.api_cache import ApiCache
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.providers.sportmonks_provider import (
    WORLD_CUP_2026_LEAGUE_ID,
    SportmonksProvider,
)

logger = logging.getLogger(__name__)

LOOKUP_CACHE_ENDPOINT = "sportmonks_fixture_lookup"
DATE_CACHE_ENDPOINT = "sportmonks_fixtures_by_date"
LOOKUP_SUCCESS_TTL_SECONDS = 86400
LOOKUP_NOT_FOUND_TTL_SECONDS = 3600
DATE_LIST_TTL_SECONDS = 1800

LOOKUP_INCLUDES = (
    "participants",
    "scores",
    "statistics",
    "lineups",
    "sidelined.sideline",
    "formations",
)

_TEAM_ALIASES: dict[str, frozenset[str]] = {
    "mexico": frozenset({"mexico"}),
    "south korea": frozenset(
        {"south korea", "korea republic", "republic of korea", "korea", "south korea republic"}
    ),
    "korea republic": frozenset(
        {"south korea", "korea republic", "republic of korea", "korea", "south korea republic"}
    ),
    "usa": frozenset({"usa", "united states", "united states of america", "u.s.a.", "us"}),
    "united states": frozenset({"usa", "united states", "united states of america", "u.s.a.", "us"}),
    "england": frozenset({"england"}),
    "cote d'ivoire": frozenset({"ivory coast", "cote d'ivoire", "côte d'ivoire"}),
    "ivory coast": frozenset({"ivory coast", "cote d'ivoire", "côte d'ivoire"}),
}


@dataclass(frozen=True)
class SportmonksFixtureLookupResult:
    found: bool
    sportmonks_fixture_id: int | None
    fixture: dict[str, Any] | None
    endpoint: str
    status_code: int | None
    reason: str
    from_cache: bool = False


def _normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = re.sub(r"[^\w\s&'-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _alias_set(name: str) -> frozenset[str]:
    key = _normalize_name(name)
    if key in _TEAM_ALIASES:
        return _TEAM_ALIASES[key]
    return frozenset({key})


def team_names_match(expected: str, candidate: str) -> bool:
    expected_aliases = _alias_set(expected)
    candidate_key = _normalize_name(candidate)
    if not candidate_key:
        return False
    if candidate_key in expected_aliases:
        return True
    for alias in expected_aliases:
        if alias in candidate_key or candidate_key in alias:
            return True
    return False


def _lookup_cache(settings: Settings) -> ApiCache:
    cache_dir = Path(settings.api_cache_dir) / "sportmonks"
    return ApiCache(cache_dir, default_ttl_seconds=LOOKUP_SUCCESS_TTL_SECONDS)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _participant_side(participant: dict[str, Any]) -> str:
    meta = participant.get("meta") or {}
    return str(meta.get("location") or "").lower()


def _fixture_participants(item: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in (item.get("participants") or []) if isinstance(p, dict)]


def _is_world_cup_fixture(item: dict[str, Any]) -> bool:
    league_id = item.get("league_id")
    try:
        return int(league_id) == WORLD_CUP_2026_LEAGUE_ID
    except (TypeError, ValueError):
        return False


def _match_fixture_item(
    item: dict[str, Any],
    *,
    home_team: str,
    away_team: str,
) -> bool:
    if not _is_world_cup_fixture(item):
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
) -> tuple[list[dict[str, Any]], int | None, str | None]:
    date_str = day.isoformat()
    cache_params = {"date": date_str, "league_id": WORLD_CUP_2026_LEAGUE_ID}
    cached = cache.get(DATE_CACHE_ENDPOINT, cache_params)
    if isinstance(cached, dict) and isinstance(cached.get("items"), list):
        return cached["items"], 200, None

    endpoint = f"/fixtures/date/{date_str}"
    status, payload, error = provider.safe_get(
        endpoint,
        params={
            "include": _include_string(),
            "filters": f"fixtureLeagues:{WORLD_CUP_2026_LEAGUE_ID}",
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


def lookup_world_cup_fixture(
    *,
    api_fixture_id: int,
    home_team: str,
    away_team: str,
    kickoff_date: str | None,
    settings: Settings | None = None,
) -> SportmonksFixtureLookupResult:
    """
    Resolve API-Football fixture to Sportmonks fixture — cache-first, WC league guard.

    Uses GET /fixtures/date/{date} with fixtureLeagues:732 (not /fixtures/search).
    """
    settings = settings or get_settings()
    cache = _lookup_cache(settings)
    cache_params = {
        "api_fixture_id": int(api_fixture_id),
        "home_team": _normalize_name(home_team),
        "away_team": _normalize_name(away_team),
        "kickoff_date": (kickoff_date or "")[:10],
    }
    cached = cache.get(LOOKUP_CACHE_ENDPOINT, cache_params)
    if isinstance(cached, dict):
        if cached.get("status") == "found" and isinstance(cached.get("fixture"), dict):
            return SportmonksFixtureLookupResult(
                found=True,
                sportmonks_fixture_id=int(cached.get("sportmonks_fixture_id")),
                fixture=cached["fixture"],
                endpoint=str(cached.get("endpoint") or f"/fixtures/date/{kickoff_date}"),
                status_code=200,
                reason="cache_hit",
                from_cache=True,
            )
        if cached.get("status") == "not_found":
            return SportmonksFixtureLookupResult(
                found=False,
                sportmonks_fixture_id=None,
                fixture=None,
                endpoint=str(cached.get("endpoint") or "lookup"),
                status_code=cached.get("status_code"),
                reason=str(cached.get("reason") or "not_found"),
                from_cache=True,
            )

    provider = SportmonksProvider(settings)
    if not provider.is_configured:
        return SportmonksFixtureLookupResult(
            found=False,
            sportmonks_fixture_id=None,
            fixture=None,
            endpoint="lookup",
            status_code=None,
            reason="not_configured",
        )

    anchor = _parse_date(kickoff_date)
    if anchor is None:
        return SportmonksFixtureLookupResult(
            found=False,
            sportmonks_fixture_id=None,
            fixture=None,
            endpoint="lookup",
            status_code=None,
            reason="missing_kickoff_date",
        )

    search_days = [anchor, anchor - timedelta(days=1), anchor + timedelta(days=1)]
    last_status: int | None = None
    last_error: str | None = None
    last_endpoint = f"/fixtures/date/{anchor.isoformat()}"

    for day in search_days:
        last_endpoint = f"/fixtures/date/{day.isoformat()}"
        items, status, error = _fetch_fixtures_for_date(provider, cache, day=day)
        last_status = status
        last_error = error
        if error:
            continue
        for item in items:
            if _match_fixture_item(item, home_team=home_team, away_team=away_team):
                sm_id = int(item["id"])
                cache.set(
                    LOOKUP_CACHE_ENDPOINT,
                    cache_params,
                    {
                        "status": "found",
                        "sportmonks_fixture_id": sm_id,
                        "fixture": item,
                        "endpoint": last_endpoint,
                    },
                    ttl_seconds=LOOKUP_SUCCESS_TTL_SECONDS,
                )
                return SportmonksFixtureLookupResult(
                    found=True,
                    sportmonks_fixture_id=sm_id,
                    fixture=item,
                    endpoint=last_endpoint,
                    status_code=status,
                    reason="matched",
                )

    reason = last_error or "not_found"
    cache.set(
        LOOKUP_CACHE_ENDPOINT,
        cache_params,
        {
            "status": "not_found",
            "reason": reason,
            "endpoint": last_endpoint,
            "status_code": last_status,
        },
        ttl_seconds=LOOKUP_NOT_FOUND_TTL_SECONDS,
    )
    return SportmonksFixtureLookupResult(
        found=False,
        sportmonks_fixture_id=None,
        fixture=None,
        endpoint=last_endpoint,
        status_code=last_status,
        reason=reason,
    )
