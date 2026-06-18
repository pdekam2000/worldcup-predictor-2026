"""Single-threaded API request queue with 429 retry — Phase 40A."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ApiRequestThrottle:
    """Serialize API calls with configurable delay and automatic 429 backoff."""

    def __init__(
        self,
        *,
        base_delay_seconds: float = 1.0,
        warning_delay_seconds: float = 2.0,
        rate_limit_delay_seconds: float = 5.0,
        max_retries: int = 3,
    ) -> None:
        self._base_delay = base_delay_seconds
        self._warning_delay = warning_delay_seconds
        self._rate_limit_delay = rate_limit_delay_seconds
        self._max_retries = max_retries
        self._lock = threading.Lock()
        self._last_request_at = 0.0
        self._warning_mode = False

    def wait_before_request(self, *, after_warning: bool = False, after_429: bool = False) -> None:
        if after_429:
            delay = self._rate_limit_delay
        elif after_warning or self._warning_mode:
            delay = self._warning_delay
        else:
            delay = self._base_delay
        with self._lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < delay:
                time.sleep(delay - elapsed)
            self._last_request_at = time.monotonic()

    def execute(self, fn: Callable[[], T], *, quota_tracker: Any | None = None) -> T:
        """Run fn with pre-delay and retry on HTTP 429 / rate-limit errors."""
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            after_429 = attempt > 0
            self.wait_before_request(after_429=after_429)
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                if not _is_rate_limit_error(exc):
                    raise
                self._warning_mode = True
                if quota_tracker is not None:
                    quota_tracker.record_rate_limit_retry()
                logger.warning("API rate limit hit (attempt %s/%s): %s", attempt + 1, self._max_retries + 1, exc)
                if attempt >= self._max_retries:
                    break
        assert last_exc is not None
        raise last_exc


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    if "429" in text or "rate limit" in text or "request limit" in text:
        return True
    status = getattr(exc, "response", None)
    if status is not None and getattr(status, "status_code", None) == 429:
        return True
    return False
