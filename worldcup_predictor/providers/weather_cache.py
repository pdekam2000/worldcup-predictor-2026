"""Cache-first weather forecast storage — Phase 43."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.cache.api_cache import ApiCache
from worldcup_predictor.config.settings import Settings, get_settings


def _cache(settings: Settings) -> ApiCache:
    from pathlib import Path

    cache_dir = Path(settings.api_cache_dir) / "weather"
    ttl = int(getattr(settings, "weather_cache_ttl_seconds", settings.api_cache_ttl_seconds))
    return ApiCache(cache_dir, default_ttl_seconds=ttl)


def weather_cache_get(
    provider: str,
    query: str,
    *,
    kickoff_iso: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    params = {"provider": provider, "query": query, "kickoff": kickoff_iso or ""}
    payload = _cache(settings).get("weather_forecast", params)
    return dict(payload) if isinstance(payload, dict) else None


def weather_cache_set(
    provider: str,
    query: str,
    payload: dict[str, Any],
    *,
    kickoff_iso: str | None = None,
    settings: Settings | None = None,
    ttl_seconds: int | None = None,
) -> None:
    settings = settings or get_settings()
    params = {"provider": provider, "query": query, "kickoff": kickoff_iso or ""}
    ttl = ttl_seconds if ttl_seconds is not None else int(
        getattr(settings, "weather_cache_ttl_seconds", settings.api_cache_ttl_seconds)
    )
    _cache(settings).set("weather_forecast", params, payload, ttl_seconds=ttl)
