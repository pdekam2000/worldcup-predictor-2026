"""Phase 39B-2 — checkout creation rate limits (in-memory per process)."""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_buckets: dict[str, list[float]] = {}

CHECKOUT_MAX_PER_HOUR = 5
CHECKOUT_MIN_INTERVAL_SECONDS = 30


def check_checkout_allowed(*, user_id: str) -> tuple[bool, int]:
    key = f"checkout:{user_id}"
    now = time.time()
    with _lock:
        window = [t for t in _buckets.get(key, []) if now - t < 3600]
        if window and now - window[-1] < CHECKOUT_MIN_INTERVAL_SECONDS:
            return False, int(CHECKOUT_MIN_INTERVAL_SECONDS - (now - window[-1]))
        if len(window) >= CHECKOUT_MAX_PER_HOUR:
            return False, int(3600 - (now - window[0]))
    return True, 0


def record_checkout_attempt(*, user_id: str) -> None:
    key = f"checkout:{user_id}"
    with _lock:
        now = time.time()
        window = [t for t in _buckets.get(key, []) if now - t < 3600]
        window.append(now)
        _buckets[key] = window


def reset_checkout_rate_limits() -> None:
    with _lock:
        _buckets.clear()
