"""File cache for full prediction API responses — quota protection."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from worldcup_predictor.cache.api_cache import ApiCache
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.quota.cache_policy import prediction_result_ttl_seconds
from worldcup_predictor.quota.quota_tracker import get_quota_tracker

_lock = threading.Lock()
_cache_singleton: ApiCache | None = None


def _cache(settings: Settings | None = None) -> ApiCache:
    global _cache_singleton
    settings = settings or get_settings()
    with _lock:
        if _cache_singleton is None:
            cache_dir = Path(settings.prediction_cache_dir)
            _cache_singleton = ApiCache(cache_dir, default_ttl_seconds=3600)
        return _cache_singleton


def _cache_params(
    fixture_id: int,
    *,
    competition_key: str,
    season: int,
    locale: str,
) -> dict[str, Any]:
    return {
        "fixture_id": fixture_id,
        "competition": competition_key,
        "season": season,
        "locale": locale,
    }


def _parse_kickoff(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def get_cached_prediction(
    fixture_id: int,
    *,
    competition_key: str,
    season: int,
    locale: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    payload = _cache(settings).get(
        "prediction_result",
        _cache_params(fixture_id, competition_key=competition_key, season=season, locale=locale),
    )
    if payload is None:
        get_quota_tracker().record_prediction_cache_miss()
        return None
    get_quota_tracker().record_prediction_cache_hit()
    out = dict(payload)
    out["cache_source"] = "cache"
    return out


def store_prediction(
    fixture_id: int,
    payload: dict[str, Any],
    *,
    competition_key: str,
    season: int,
    locale: str,
    kickoff_utc: datetime | None = None,
    settings: Settings | None = None,
) -> None:
    ttl = prediction_result_ttl_seconds(kickoff_utc)
    enriched = dict(payload)
    enriched["cached_at"] = time.time()
    enriched["cache_source"] = enriched.get("cache_source", "live")
    if kickoff_utc is not None:
        enriched["kickoff_utc"] = kickoff_utc.isoformat()
    _cache(settings).set(
        "prediction_result",
        _cache_params(fixture_id, competition_key=competition_key, season=season, locale=locale),
        enriched,
        ttl_seconds=ttl,
    )


def kickoff_from_payload(payload: dict[str, Any]) -> datetime | None:
    return _parse_kickoff(payload.get("kickoff_utc"))
