"""Sportmonks World Cup 2026 standings — cache-first daily fetch (Phase 22E)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from worldcup_predictor.cache.api_cache import ApiCache
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.providers.sportmonks_provider import (
    WORLD_CUP_2026_LEAGUE_ID,
    WORLD_CUP_2026_SEASON_ID,
    SportmonksProvider,
)
from worldcup_predictor.quota.cache_policy import DAILY_TTL_SECONDS

logger = logging.getLogger(__name__)

STANDINGS_CACHE_ENDPOINT = "sportmonks_standings_by_season"
STANDINGS_INCLUDES = ("participant", "details", "form", "group", "stage", "rule")


def _standings_cache(settings: Settings) -> ApiCache:
    cache_dir = Path(settings.api_cache_dir) / "sportmonks"
    return ApiCache(cache_dir, default_ttl_seconds=DAILY_TTL_SECONDS)


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _team_name_from_row(row: dict[str, Any]) -> str:
    participant = row.get("participant")
    if isinstance(participant, dict):
        return str(participant.get("name") or participant.get("short_code") or "")
    return str(row.get("participant_name") or "")


def _goal_difference_from_details(details: Any) -> int | None:
    for entry in _safe_list(details):
        if not isinstance(entry, dict):
            continue
        type_block = entry.get("type")
        label = ""
        if isinstance(type_block, dict):
            label = str(type_block.get("name") or type_block.get("developer_name") or "").lower()
        if "goal" in label and "diff" in label:
            val = entry.get("value")
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return None


def normalize_sportmonks_standings_payload(payload: Any) -> dict[str, Any]:
    """Normalize Sportmonks standings response into team-indexed rows."""
    if not isinstance(payload, dict):
        return {"available": False, "teams": {}, "groups": {}}

    data = payload.get("data")
    rows = _safe_list(data)
    teams: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _team_name_from_row(row)
        if not name:
            continue
        group_block = row.get("group")
        group_name = ""
        if isinstance(group_block, dict):
            group_name = str(group_block.get("name") or group_block.get("short_name") or "")
        position = row.get("position") or row.get("rank")
        points = row.get("points")
        try:
            pos_i = int(position) if position is not None else None
        except (TypeError, ValueError):
            pos_i = None
        try:
            pts_i = int(points) if points is not None else None
        except (TypeError, ValueError):
            pts_i = None
        gd = _goal_difference_from_details(row.get("details"))
        if gd is None:
            try:
                gd = int(row.get("goal_difference")) if row.get("goal_difference") is not None else None
            except (TypeError, ValueError):
                gd = None

        form_raw = row.get("form")
        form_str = str(form_raw) if form_raw not in (None, "") else ""

        entry = {
            "team_name": name,
            "group_position": pos_i,
            "points": pts_i,
            "goal_difference": gd,
            "group_name": group_name,
            "form": form_str,
            "participant_id": row.get("participant_id"),
            "source": "sportmonks",
        }
        teams[name.lower()] = entry
        if group_name:
            groups.setdefault(group_name, []).append(entry)

    for group_name, items in groups.items():
        groups[group_name] = sorted(
            items,
            key=lambda x: (x.get("group_position") is None, x.get("group_position") or 99),
        )

    return {
        "available": bool(teams),
        "teams": teams,
        "groups": groups,
        "team_count": len(teams),
        "group_count": len(groups),
        "source": "sportmonks",
        "season_id": WORLD_CUP_2026_SEASON_ID,
        "league_id": WORLD_CUP_2026_LEAGUE_ID,
    }


def fetch_worldcup_standings(
    *,
    settings: Settings | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Fetch WC standings by season — one API call max per daily cache window."""
    settings = settings or get_settings()
    provider = SportmonksProvider(settings)
    cache = _standings_cache(settings)
    cache_params = {"season_id": WORLD_CUP_2026_SEASON_ID, "league_id": WORLD_CUP_2026_LEAGUE_ID}

    if not provider.is_configured:
        return {
            "available": False,
            "source": "none",
            "message": "Sportmonks not configured",
            "teams": {},
            "groups": {},
        }

    if not force_refresh:
        cached = cache.get(STANDINGS_CACHE_ENDPOINT, cache_params)
        if isinstance(cached, dict) and cached.get("available") is not None:
            cached = dict(cached)
            cached["from_cache"] = True
            return cached

    endpoint = f"/standings/seasons/{WORLD_CUP_2026_SEASON_ID}"
    status, payload, error = provider.safe_get(
        endpoint,
        params={"include": ";".join(STANDINGS_INCLUDES)},
    )
    if error or not isinstance(payload, dict):
        return {
            "available": False,
            "source": "api",
            "message": error or "empty standings response",
            "status_code": status,
            "teams": {},
            "groups": {},
        }

    normalized = normalize_sportmonks_standings_payload(payload)
    normalized["endpoint"] = endpoint
    normalized["status_code"] = status
    normalized["from_cache"] = False
    normalized["includes"] = list(STANDINGS_INCLUDES)
    normalized["message"] = (
        f"Fetched {normalized.get('team_count', 0)} teams across "
        f"{normalized.get('group_count', 0)} groups."
    )

    cache.set(STANDINGS_CACHE_ENDPOINT, cache_params, normalized, ttl_seconds=DAILY_TTL_SECONDS)
    return normalized


def lookup_team_standings(standings_block: dict[str, Any], team_name: str) -> dict[str, Any] | None:
    teams = standings_block.get("teams") if isinstance(standings_block, dict) else None
    if not isinstance(teams, dict):
        return None
    key = (team_name or "").lower()
    if key in teams:
        return teams[key]
    for name, row in teams.items():
        if key in name or name in key:
            return row
    return None
