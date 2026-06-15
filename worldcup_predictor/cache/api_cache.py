from __future__ import annotations

import hashlib
import json
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings


class ApiCache:
    """TTL-based JSON file cache keyed by endpoint + params."""

    def __init__(self, cache_dir: Path, default_ttl_seconds: int = 3600) -> None:
        self._cache_dir = cache_dir
        self._default_ttl = default_ttl_seconds
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def build_key(endpoint: str, params: dict[str, Any]) -> str:
        normalized = json.dumps(params, sort_keys=True, default=str)
        digest = hashlib.sha256(f"{endpoint}:{normalized}".encode()).hexdigest()
        return digest

    def _path_for(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    def get(self, endpoint: str, params: dict[str, Any]) -> Any | None:
        key = self.build_key(endpoint, params)
        path = self._path_for(key)
        if not path.exists():
            return None

        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        expires_at = envelope.get("expires_at", 0)
        if time.time() > expires_at:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None

        return envelope.get("payload")

    def set(
        self,
        endpoint: str,
        params: dict[str, Any],
        payload: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        key = self.build_key(endpoint, params)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        envelope = {
            "endpoint": endpoint,
            "params": params,
            "cached_at": time.time(),
            "expires_at": time.time() + ttl,
            "payload": payload,
        }
        self._path_for(key).write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear_expired(self) -> int:
        removed = 0
        now = time.time()
        for path in self._cache_dir.glob("*.json"):
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
                if now > envelope.get("expires_at", 0):
                    path.unlink(missing_ok=True)
                    removed += 1
            except (json.JSONDecodeError, OSError):
                try:
                    path.unlink(missing_ok=True)
                    removed += 1
                except OSError:
                    pass
        return removed


@lru_cache
def get_api_cache(cache_dir: str | None = None, ttl_seconds: int | None = None) -> ApiCache:
    active = get_settings()
    resolved_dir = cache_dir or active.api_cache_dir
    resolved_ttl = ttl_seconds if ttl_seconds is not None else active.api_cache_ttl_seconds
    return ApiCache(cache_dir=Path(resolved_dir), default_ttl_seconds=resolved_ttl)
