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
from worldcup_predictor.quota.prediction_cache_policy import (
    is_prediction_cache_valid,
    stamp_prediction_cache,
)
from worldcup_predictor.quota.quota_tracker import get_quota_tracker

try:
    from worldcup_predictor.automation.worldcup_background.freshness import is_prediction_fresh
except ImportError:
    is_prediction_fresh = None  # type: ignore[assignment]

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

    valid, reason = is_prediction_cache_valid(payload)
    if not valid:
        get_quota_tracker().record_prediction_cache_miss()
        return None

    if is_prediction_fresh is not None:
        fresh, fresh_reason = is_prediction_fresh(payload, kickoff_utc=kickoff_from_payload(payload))
        if not fresh:
            get_quota_tracker().record_prediction_cache_miss()
            return None
        reason = fresh_reason

    from worldcup_predictor.automation.worldcup_background.stale_prediction_policy import (
        is_stored_prediction_quality_valid,
    )

    quality_ok, quality_reason = is_stored_prediction_quality_valid(payload)
    if not quality_ok:
        get_quota_tracker().record_prediction_cache_miss()
        return None

    get_quota_tracker().record_prediction_cache_hit()
    out = dict(payload)
    out["cache_source"] = "cache"
    out["cache_validated"] = True
    out["cache_validation_reason"] = reason
    out["quality_validation_reason"] = quality_reason
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
    prediction_is_placeholder: bool | None = None,
    existing_payload: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    settings = settings or get_settings()
    from worldcup_predictor.automation.worldcup_background.prediction_store_guard import evaluate_prediction_storage

    allow, reason = evaluate_prediction_storage(
        payload,
        settings=settings,
        prediction_is_placeholder=prediction_is_placeholder,
        existing_payload=existing_payload,
    )
    if not allow:
        return False, reason

    ttl = prediction_result_ttl_seconds(kickoff_utc)
    enriched = stamp_prediction_cache(dict(payload))
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
    return True, "ok"


def kickoff_from_payload(payload: dict[str, Any]) -> datetime | None:
    return _parse_kickoff(payload.get("kickoff_utc"))
