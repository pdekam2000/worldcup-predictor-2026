"""Resolved active season cache — Phase A10 (no hardcoded season years)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings

_lock = threading.Lock()
_memory: dict[str, tuple[float, int]] = {}
_DEFAULT_TTL = 6 * 3600


def _cache_path(settings: Settings) -> Path:
    root = Path(settings.sqlite_path or "data/football_intelligence.db").parent
    return root / "cache" / "resolved_seasons.json"


def _load_disk(settings: Settings) -> dict[str, Any]:
    path = _cache_path(settings)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_disk(settings: Settings, data: dict[str, Any]) -> None:
    path = _cache_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_cached_season(competition_key: str, *, settings: Settings | None = None) -> int | None:
    settings = settings or get_settings()
    ttl = int(getattr(settings, "season_resolve_cache_ttl_seconds", _DEFAULT_TTL) or _DEFAULT_TTL)
    now = time.time()
    with _lock:
        mem = _memory.get(competition_key)
        if mem and mem[0] > now:
            return mem[1]
    disk = _load_disk(settings)
    entry = disk.get(competition_key)
    if not entry:
        return None
    if float(entry.get("expires_at") or 0) < now:
        return None
    season = entry.get("season")
    if season is None:
        return None
    with _lock:
        _memory[competition_key] = (float(entry["expires_at"]), int(season))
    return int(season)


def set_cached_season(
    competition_key: str,
    season: int,
    *,
    settings: Settings | None = None,
    source: str = "resolver",
) -> None:
    settings = settings or get_settings()
    ttl = int(getattr(settings, "season_resolve_cache_ttl_seconds", _DEFAULT_TTL) or _DEFAULT_TTL)
    expires = time.time() + ttl
    with _lock:
        _memory[competition_key] = (expires, int(season))
        disk = _load_disk(settings)
        disk[competition_key] = {
            "season": int(season),
            "expires_at": expires,
            "resolved_at": time.time(),
            "source": source,
        }
        _save_disk(settings, disk)


def cache_stats(*, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    disk = _load_disk(settings)
    now = time.time()
    valid = sum(1 for v in disk.values() if float(v.get("expires_at") or 0) > now)
    return {"entries": len(disk), "valid_entries": valid}
