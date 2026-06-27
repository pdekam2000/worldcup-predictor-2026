"""Per-competition schedule cache for Match Center — Phase A10."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.domain.schedule import TournamentFixture

_lock = threading.Lock()
_entries: dict[str, "ScheduleCacheEntry"] = {}


@dataclass
class ScheduleCacheEntry:
    fixtures: list[TournamentFixture] = field(default_factory=list)
    source_label: str | None = None
    season: int = 0
    expires_at: float = 0.0
    cache_hit: bool = False


def _key(competition_key: str, season: int) -> str:
    return f"{competition_key}:{season}"


def get_schedule_cache(
    competition_key: str,
    season: int,
    *,
    settings: Settings | None = None,
) -> ScheduleCacheEntry | None:
    settings = settings or get_settings()
    ttl = int(getattr(settings, "match_schedule_cache_ttl_seconds", 300) or 300)
    k = _key(competition_key, season)
    now = time.time()
    with _lock:
        entry = _entries.get(k)
        if entry is None or entry.expires_at < now:
            return None
        out = ScheduleCacheEntry(
            fixtures=list(entry.fixtures),
            source_label=entry.source_label,
            season=entry.season,
            expires_at=entry.expires_at,
            cache_hit=True,
        )
        return out


def set_schedule_cache(
    competition_key: str,
    season: int,
    fixtures: list[TournamentFixture],
    *,
    source_label: str | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    ttl = int(getattr(settings, "match_schedule_cache_ttl_seconds", 300) or 300)
    k = _key(competition_key, season)
    with _lock:
        _entries[k] = ScheduleCacheEntry(
            fixtures=list(fixtures),
            source_label=source_label,
            season=season,
            expires_at=time.time() + ttl,
            cache_hit=False,
        )


def cache_stats() -> dict[str, Any]:
    now = time.time()
    with _lock:
        valid = sum(1 for e in _entries.values() if e.expires_at >= now)
        return {"entries": len(_entries), "valid_entries": valid}
