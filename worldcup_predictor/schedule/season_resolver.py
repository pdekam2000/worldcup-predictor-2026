"""Auto-resolve active API-Football season per competition — Phase A10."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.competitions import (
    DEFAULT_COMPETITION_KEY,
    CompetitionConfig,
    get_competition,
)
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.quota.season_resolve_cache import get_cached_season, set_cached_season

logger = logging.getLogger(__name__)

_UPCOMING = frozenset({"NS", "TBD", "SCHEDULED", "TIMED", "1H", "HT", "2H", "LIVE"})


def _season_candidates(reference: datetime | None = None) -> list[int]:
    """Derive candidate seasons from calendar — never hardcode fixed years."""
    ref = reference or datetime.now(timezone.utc)
    year = ref.year
    if ref.month >= 6:
        primary = [year, year - 1]
    else:
        primary = [year - 1, year]
    # Include registry hint as fallback candidate only
    out: list[int] = []
    for y in primary:
        if y not in out:
            out.append(y)
    return out


def _is_world_cup_locked(comp: CompetitionConfig) -> bool:
    return comp.key == DEFAULT_COMPETITION_KEY or (
        comp.compensation_type == "tournament" and comp.key.startswith("world_cup")
    )


def _count_upcoming_fixtures(items: list[dict[str, Any]]) -> int:
    n = 0
    for item in items:
        fixture = item.get("fixture") or {}
        status = str((fixture.get("status") or {}).get("short") or "").upper()
        if status in _UPCOMING:
            n += 1
    return n


def resolve_active_season(
    competition_key: str,
    *,
    settings: Settings | None = None,
    force_refresh: bool = False,
) -> int:
    """Return active season for competition; World Cup uses registry season unchanged."""
    settings = settings or get_settings()
    comp = get_competition(competition_key)

    if _is_world_cup_locked(comp):
        return comp.season

    if not force_refresh:
        cached = get_cached_season(comp.key, settings=settings)
        if cached is not None:
            return cached

    if not comp.league_id_configured:
        set_cached_season(comp.key, comp.season, settings=settings, source="registry_fallback")
        return comp.season

    best_season = comp.season
    best_count = -1
    try:
        from worldcup_predictor.clients.api_football import ApiFootballClient

        client = ApiFootballClient(settings)
        if not client.is_configured:
            set_cached_season(comp.key, comp.season, settings=settings, source="registry_no_api")
            return comp.season

        for season in _season_candidates():
            result = client._safe_get(  # noqa: SLF001
                "fixtures",
                {"league": comp.league_id, "season": season, "next": 15},
                placeholder_factory=list,
                ttl_seconds=300,
            )
            items = result.data if isinstance(result.data, list) else []
            count = _count_upcoming_fixtures(items)
            if count > best_count:
                best_count = count
                best_season = season
    except Exception as exc:
        logger.warning("Season resolve failed for %s: %s", competition_key, exc)
        best_season = comp.season

    set_cached_season(comp.key, best_season, settings=settings, source="provider_probe")
    return best_season


def resolve_all_enabled_seasons(
    competition_keys: list[str] | None = None,
    *,
    settings: Settings | None = None,
) -> dict[str, int]:
    from worldcup_predictor.config.competitions import list_competition_keys

    settings = settings or get_settings()
    keys = competition_keys or list_competition_keys(enabled_only=True)
    return {k: resolve_active_season(k, settings=settings) for k in keys}
