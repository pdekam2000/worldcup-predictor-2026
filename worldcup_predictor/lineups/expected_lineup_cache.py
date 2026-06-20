"""Cache gate for expected lineup intelligence — aggressive cache, kickoff-aware."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from worldcup_predictor.cache.api_cache import ApiCache
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.quota.cache_policy import (
    LINEUPS_TTL_NEAR_SECONDS,
    should_fetch_lineups,
)

CACHE_ENDPOINT = "expected_lineup_intelligence"
FAR_KICKOFF_TTL_SECONDS = 3600


def _lineup_cache(settings: Settings) -> ApiCache:
    cache_dir = Path(settings.api_cache_dir) / "lineups"
    return ApiCache(cache_dir, default_ttl_seconds=LINEUPS_TTL_NEAR_SECONDS)


def ttl_for_kickoff(kickoff_utc: datetime | None) -> int:
    if kickoff_utc is None:
        return LINEUPS_TTL_NEAR_SECONDS
    if should_fetch_lineups(kickoff_utc):
        return LINEUPS_TTL_NEAR_SECONDS
    return FAR_KICKOFF_TTL_SECONDS


def get_cached_expected_lineup(
    fixture_id: int,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    cache = _lineup_cache(settings)
    payload = cache.get(CACHE_ENDPOINT, {"fixture_id": fixture_id})
    return payload if isinstance(payload, dict) else None


def cache_expected_lineup(
    fixture_id: int,
    payload: dict[str, Any],
    *,
    kickoff_utc: datetime | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    cache = _lineup_cache(settings)
    ttl = ttl_for_kickoff(kickoff_utc)
    cache.set(CACHE_ENDPOINT, {"fixture_id": fixture_id}, payload, ttl_seconds=ttl)


def get_or_build_expected_lineup(
    fixture_id: int,
    *,
    kickoff_utc: datetime | None,
    build_fn: Callable[[], dict[str, Any]],
    settings: Settings | None = None,
    force_refresh: bool = False,
) -> tuple[dict[str, Any], bool]:
    """
    Return (payload, from_cache).

    Near kickoff: shorter TTL. Far from kickoff: reuse cache aggressively, skip rebuild.
    """
    settings = settings or get_settings()
    if not force_refresh:
        cached = get_cached_expected_lineup(fixture_id, settings=settings)
        if cached is not None:
            if not should_fetch_lineups(kickoff_utc):
                return cached, True
            cached_ts = cached.get("cached_at")
            if cached_ts and should_fetch_lineups(kickoff_utc):
                return cached, True

    if not should_fetch_lineups(kickoff_utc):
        cached = get_cached_expected_lineup(fixture_id, settings=settings)
        if cached is not None:
            return cached, True
        payload = build_fn()
        payload["cached_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        cache_expected_lineup(fixture_id, payload, kickoff_utc=kickoff_utc, settings=settings)
        return payload, False

    payload = build_fn()
    payload["cached_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    cache_expected_lineup(fixture_id, payload, kickoff_utc=kickoff_utc, settings=settings)
    return payload, False
