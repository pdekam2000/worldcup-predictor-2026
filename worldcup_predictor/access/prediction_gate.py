"""Prediction quota gate — checked before API/pipeline calls."""

from __future__ import annotations

from dataclasses import dataclass

from worldcup_predictor.access.config import free_daily_prediction_limit, public_access_enabled
from worldcup_predictor.access.identity import current_user_id, is_registered_user
from worldcup_predictor.access.models import utc_today
from worldcup_predictor.access.repository import AccessRepository, get_access_repository


@dataclass
class GateCheckResult:
    allowed: bool
    reason: str = ""
    remaining: int | None = None
    used_today: int = 0
    daily_limit: int = 2
    is_paid: bool = False
    show_upgrade: bool = False
    user_id: str = ""


def _repo() -> AccessRepository:
    return get_access_repository()


def _paid_active(user_id: str) -> bool:
    ent = _repo().get_entitlement(user_id)
    if not ent.paid:
        return False
    if not ent.expires_at:
        return True
    try:
        from datetime import datetime, timezone

        exp = datetime.fromisoformat(ent.expires_at.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp > datetime.now(timezone.utc)
    except Exception:
        return True


def _login_required_result() -> GateCheckResult:
    limit = free_daily_prediction_limit()
    return GateCheckResult(
        allowed=False,
        reason="login_required",
        remaining=0,
        used_today=0,
        daily_limit=limit,
        show_upgrade=False,
    )


def preview_prediction_quota(user_id: str | None = None) -> GateCheckResult:
    """Read-only quota check — does not increment."""
    if not public_access_enabled():
        return GateCheckResult(allowed=True, user_id=user_id or "local_dev", is_paid=True, remaining=999)

    if user_id is None and not is_registered_user():
        return _login_required_result()

    uid = user_id or current_user_id()
    limit = free_daily_prediction_limit()
    if _paid_active(uid):
        used = _repo().get_usage_count(uid, utc_today())
        return GateCheckResult(
            allowed=True,
            user_id=uid,
            is_paid=True,
            used_today=used,
            daily_limit=limit,
            remaining=999,
        )

    used = _repo().get_usage_count(uid, utc_today())
    remaining = max(0, limit - used)
    allowed = used < limit
    return GateCheckResult(
        allowed=allowed,
        user_id=uid,
        is_paid=False,
        used_today=used,
        daily_limit=limit,
        remaining=remaining,
        show_upgrade=not allowed,
        reason="" if allowed else "daily_limit_reached",
    )


def preview_api_access(user_id: str | None = None) -> GateCheckResult:
    """Same as quota preview — blocks API-Football when free limit exhausted."""
    return preview_prediction_quota(user_id)


def acquire_prediction_slot(user_id: str | None = None) -> GateCheckResult:
    """Check quota and atomically consume one prediction slot before pipeline/API."""
    preview = preview_prediction_quota(user_id)
    if not preview.allowed:
        if preview.reason == "login_required":
            return preview
        preview.show_upgrade = True
        preview.reason = "daily_limit_reached"
        return preview

    if not public_access_enabled() or preview.is_paid:
        return preview

    uid = preview.user_id
    limit = preview.daily_limit
    ok, new_count = _repo().try_increment_prediction(uid, daily_limit=limit)
    if ok:
        preview.used_today = new_count
        preview.remaining = max(0, limit - new_count)
        preview.allowed = True
        return preview

    preview.allowed = False
    preview.used_today = new_count
    preview.remaining = 0
    preview.show_upgrade = True
    preview.reason = "daily_limit_reached"
    return preview
