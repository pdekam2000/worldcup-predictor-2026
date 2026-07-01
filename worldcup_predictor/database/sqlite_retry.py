"""Safe SQLite write retry with exponential backoff."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

DEFAULT_MAX_ATTEMPTS = 6
DEFAULT_BASE_DELAY_S = 0.5
DEFAULT_MAX_DELAY_S = 8.0


def is_sqlite_lock_error(exc: BaseException) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower()


def run_with_sqlite_retry(
    fn: Callable[[], T],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    max_delay_s: float = DEFAULT_MAX_DELAY_S,
) -> T:
    last_exc: sqlite3.OperationalError | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            if not is_sqlite_lock_error(exc):
                raise
            last_exc = exc
            if attempt + 1 >= max_attempts:
                break
            time.sleep(min(max_delay_s, base_delay_s * (2**attempt)))
    raise sqlite3.OperationalError(
        f"SQLite database is locked after {max_attempts} attempts"
    ) from last_exc
