"""Track API quota efficiency — Phase 40A."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


@dataclass
class QuotaSnapshot:
    stat_date: str
    live_requests: int = 0
    cache_hits: int = 0
    local_hits: int = 0
    calls_saved: int = 0
    rate_limit_retries: int = 0
    last_sync_at: str | None = None

    @property
    def total_attempts(self) -> int:
        return self.live_requests + self.cache_hits + self.local_hits

    @property
    def cache_hit_rate(self) -> float | None:
        total = self.total_attempts
        if total == 0:
            return None
        return round((self.cache_hits + self.local_hits) / total, 4)

    @property
    def quota_efficiency(self) -> float | None:
        """Share of requests avoided vs would-be live calls."""
        total = self.total_attempts
        if total == 0:
            return None
        return round(self.calls_saved / max(total + self.calls_saved, 1), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stat_date": self.stat_date,
            "live_requests": self.live_requests,
            "cache_hits": self.cache_hits,
            "local_hits": self.local_hits,
            "calls_saved": self.calls_saved,
            "rate_limit_retries": self.rate_limit_retries,
            "cache_hit_rate": self.cache_hit_rate,
            "quota_efficiency": self.quota_efficiency,
            "last_sync_at": self.last_sync_at,
        }


class QuotaTracker:
    """In-memory quota counters with optional SQLite persistence."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = QuotaSnapshot(stat_date=_utc_today())
        self._repo = None

    def _repo_lazy(self):
        if self._repo is None:
            try:
                from worldcup_predictor.database.repository import FootballIntelligenceRepository

                self._repo = FootballIntelligenceRepository()
            except Exception:
                self._repo = False
        return self._repo if self._repo is not False else None

    def _roll_date(self) -> None:
        today = _utc_today()
        if self._snapshot.stat_date != today:
            self._snapshot = QuotaSnapshot(stat_date=today)

    def record_live(self) -> None:
        with self._lock:
            self._roll_date()
            self._snapshot.live_requests += 1
            self._persist()

    def record_cache_hit(self) -> None:
        with self._lock:
            self._roll_date()
            self._snapshot.cache_hits += 1
            self._snapshot.calls_saved += 1
            self._persist()

    def record_local_hit(self) -> None:
        with self._lock:
            self._roll_date()
            self._snapshot.local_hits += 1
            self._snapshot.calls_saved += 1
            self._persist()

    def record_rate_limit_retry(self) -> None:
        with self._lock:
            self._roll_date()
            self._snapshot.rate_limit_retries += 1
            self._persist()

    def mark_sync(self) -> None:
        with self._lock:
            self._roll_date()
            self._snapshot.last_sync_at = _utc_now()
            self._persist()

    def snapshot(self) -> QuotaSnapshot:
        with self._lock:
            self._roll_date()
            s = self._snapshot
            return QuotaSnapshot(
                stat_date=s.stat_date,
                live_requests=s.live_requests,
                cache_hits=s.cache_hits,
                local_hits=s.local_hits,
                calls_saved=s.calls_saved,
                rate_limit_retries=s.rate_limit_retries,
                last_sync_at=s.last_sync_at,
            )

    def _persist(self) -> None:
        repo = self._repo_lazy()
        if repo is None:
            return
        try:
            repo.upsert_api_quota_stats(self._snapshot.to_dict())
        except Exception:
            pass


_tracker: QuotaTracker | None = None
_tracker_lock = threading.Lock()


def get_quota_tracker() -> QuotaTracker:
    global _tracker
    with _tracker_lock:
        if _tracker is None:
            _tracker = QuotaTracker()
        return _tracker
