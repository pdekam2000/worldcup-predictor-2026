"""Phase 33 — kickoff-aware prediction freshness rules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_dt(raw: str | datetime | None) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=None) if raw.tzinfo else raw
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def hours_until_kickoff(kickoff_utc: datetime | None, *, now: datetime | None = None) -> float | None:
    if kickoff_utc is None:
        return None
    now = now or _utc_now()
    kick = kickoff_utc.replace(tzinfo=None) if kickoff_utc.tzinfo else kickoff_utc
    return (kick - now).total_seconds() / 3600.0


def freshness_max_age_seconds(hours_until: float | None) -> int:
    """
    Phase 33 TTL bands (seconds):
    - >24h before kickoff: 12h
    - 24h–4h: 4h
    - 4h–1h: 1h
    - <1h: 15min
    - after kickoff: treat as infinitely valid (evaluation only)
    """
    if hours_until is None:
        return 12 * 3600
    if hours_until <= 0:
        return 10 * 365 * 24 * 3600
    if hours_until > 24:
        return 12 * 3600
    if hours_until > 4:
        return 4 * 3600
    if hours_until > 1:
        return 3600
    return 900


def is_prediction_fresh(
    payload: dict[str, Any],
    *,
    kickoff_utc: datetime | None = None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Return (fresh, reason) based on cached_at and kickoff bands."""
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return False, "invalid_payload"

    now = now or _utc_now()
    kick = kickoff_utc or _parse_dt(payload.get("kickoff_utc"))
    hours = hours_until_kickoff(kick, now=now)

    if hours is not None and hours <= 0:
        return True, "post_kickoff_frozen"

    cached_at = payload.get("cached_at")
    if cached_at is None:
        return False, "missing_cached_at"
    try:
        age = now.timestamp() - float(cached_at)
    except (TypeError, ValueError):
        return False, "invalid_cached_at"

    max_age = freshness_max_age_seconds(hours)
    if age <= max_age:
        return True, f"fresh_age_{int(age)}s_max_{max_age}s"
    return False, f"stale_age_{int(age)}s_max_{max_age}s"


def should_refresh_prediction(
    *,
    kickoff_utc: datetime | None,
    has_stored: bool,
    is_fresh: bool,
    force_refresh: bool = False,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Whether background/user path should run the full pipeline."""
    now = now or _utc_now()
    hours = hours_until_kickoff(kickoff_utc, now=now)
    if hours is not None and hours <= 0:
        return False, "post_kickoff_no_refresh"
    if force_refresh:
        return True, "force_refresh"
    if not has_stored:
        return True, "missing_stored"
    if not is_fresh:
        return True, "stale_stored"
    return False, "fresh_skip"
