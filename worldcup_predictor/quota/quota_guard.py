"""Daily live-request guard and per-fixture refresh cooldown."""

from __future__ import annotations

import threading
import time
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.quota.quota_tracker import get_quota_tracker


class QuotaGuardError(RuntimeError):
    """Raised when a live API refresh would exceed quota policy."""

    def __init__(self, message: str, *, code: str = "quota_blocked") -> None:
        super().__init__(message)
        self.code = code


_lock = threading.Lock()
_last_refresh: dict[str, float] = {}


def _refresh_key(fixture_id: int, user_id: str | None) -> str:
    return f"{fixture_id}:{user_id or 'anon'}"


def check_daily_live_budget(*, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    limit = int(settings.api_daily_live_limit)
    if limit <= 0:
        return
    snap = get_quota_tracker().snapshot()
    if snap.live_requests >= limit:
        raise QuotaGuardError(
            f"Daily API live-request limit reached ({snap.live_requests}/{limit}). "
            "Try again tomorrow or use cached predictions.",
            code="daily_limit",
        )


def assert_force_refresh_allowed(
    fixture_id: int,
    *,
    user_id: str | None,
    is_admin: bool,
    settings: Settings | None = None,
) -> None:
    """Non-admins must wait between forced refreshes for the same fixture."""
    if is_admin:
        return
    settings = settings or get_settings()
    cooldown = int(settings.prediction_refresh_cooldown_seconds)
    if cooldown <= 0:
        return
    key = _refresh_key(fixture_id, user_id)
    now = time.time()
    with _lock:
        last = _last_refresh.get(key)
        if last is not None and (now - last) < cooldown:
            wait = int(cooldown - (now - last))
            raise QuotaGuardError(
                f"Please wait {wait}s before refreshing this prediction again.",
                code="refresh_cooldown",
            )
        _last_refresh[key] = now


def refresh_cooldown_remaining_seconds(
    fixture_id: int,
    *,
    user_id: str | None,
    settings: Settings | None = None,
) -> int | None:
    """Seconds until force-refresh is allowed again; None if no active cooldown."""
    settings = settings or get_settings()
    cooldown = int(settings.prediction_refresh_cooldown_seconds)
    if cooldown <= 0:
        return None
    key = _refresh_key(fixture_id, user_id)
    with _lock:
        last = _last_refresh.get(key)
        if last is None:
            return None
        remaining = int(cooldown - (time.time() - last))
        return remaining if remaining > 0 else None


def quota_risk_level(*, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    limit = int(settings.api_daily_live_limit)
    snap = get_quota_tracker().snapshot()
    if limit <= 0:
        level = "unknown"
        pct = None
    else:
        pct = round(snap.live_requests / limit * 100, 1)
        if pct >= 90:
            level = "critical"
        elif pct >= 70:
            level = "warning"
        else:
            level = "ok"
    return {
        "risk_level": level,
        "live_requests_today": snap.live_requests,
        "daily_limit": limit if limit > 0 else None,
        "usage_pct": pct,
    }
