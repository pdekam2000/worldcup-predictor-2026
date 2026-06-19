"""In-process cache for lightweight /matches/upcoming responses."""

from __future__ import annotations

import threading
import time
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings

_lock = threading.Lock()
_entries: dict[str, tuple[float, dict[str, Any]]] = {}


def _key(competition: str, season: int, limit: int) -> str:
    return f"{competition}:{season}:{limit}"


def get_cached(
    competition: str,
    season: int,
    limit: int,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    ttl = int(settings.fixtures_list_cache_ttl_seconds)
    key = _key(competition, season, limit)
    now = time.time()
    with _lock:
        entry = _entries.get(key)
        if entry is None:
            return None
        expires_at, payload = entry
        if now > expires_at:
            _entries.pop(key, None)
            return None
        out = dict(payload)
        out["cache_source"] = "cache"
        return out


def store(
    competition: str,
    season: int,
    limit: int,
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    ttl = int(settings.fixtures_list_cache_ttl_seconds)
    key = _key(competition, season, limit)
    enriched = dict(payload)
    enriched["cache_source"] = enriched.get("cache_source", "live")
    with _lock:
        _entries[key] = (time.time() + ttl, enriched)
