"""User subscription quota enforcement — Phase 38A (monthly billing cycle)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from worldcup_predictor.database.postgres.enums import SubscriptionPlan
from worldcup_predictor.database.saas_factory import saas_uow
from worldcup_predictor.subscription.plan_limits import monthly_limit_for_plan, normalize_plan
from worldcup_predictor.subscription.usage_store import PredictionUsageStore


class SubscriptionQuotaError(Exception):
    def __init__(self, message: str, *, code: str = "quota_exceeded", limit: int | None = None, used: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.limit = limit
        self.used = used


@dataclass(frozen=True)
class QuotaCheckResult:
    allowed: bool
    plan: str
    monthly_limit: int
    used_this_period: int
    remaining: int
    bypass: bool = False
    message: str | None = None
    period_key: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    # Legacy Phase 34 fields
    daily_limit: int | None = None
    used_today: int = 0


def _resolve_subscription(user_id: str) -> tuple[SubscriptionPlan, datetime | None]:
    try:
        uid = uuid.UUID(str(user_id))
        with saas_uow() as uow:
            sub = uow.subscriptions.get_for_user(uid)
            if sub is None:
                return SubscriptionPlan.FREE, None
            anchor = sub.start_date or sub.created_at
            return sub.plan, anchor
    except Exception:
        return SubscriptionPlan.FREE, None


def get_user_quota_status(
    user_id: str,
    *,
    role: str = "user",
    fixture_id: int | None = None,
) -> QuotaCheckResult:
    if role in ("admin", "super_admin"):
        return QuotaCheckResult(
            allowed=True,
            plan="admin",
            monthly_limit=0,
            used_this_period=0,
            remaining=0,
            bypass=True,
            daily_limit=None,
            used_today=0,
        )

    plan_enum, anchor = _resolve_subscription(user_id)
    plan = normalize_plan(plan_enum)
    limit = monthly_limit_for_plan(plan)
    store = PredictionUsageStore()
    period = store.billing_period(anchor)
    used = store.count_period(user_id, period.key)

    if fixture_id is not None and store.has_fixture_period(user_id, period.key, fixture_id):
        return QuotaCheckResult(
            allowed=True,
            plan=plan,
            monthly_limit=limit,
            used_this_period=used,
            remaining=max(0, limit - used),
            message="Already counted for this fixture in the current billing period",
            period_key=period.key,
            period_start=period.start.isoformat(),
            period_end=period.end.isoformat(),
            daily_limit=limit,
            used_today=used,
        )

    remaining = max(0, limit - used)
    allowed = used < limit
    return QuotaCheckResult(
        allowed=allowed,
        plan=plan,
        monthly_limit=limit,
        used_this_period=used,
        remaining=remaining,
        message=None if allowed else "Monthly prediction limit reached. Upgrade your plan for more predictions.",
        period_key=period.key,
        period_start=period.start.isoformat(),
        period_end=period.end.isoformat(),
        daily_limit=limit,
        used_today=used,
    )


def assert_prediction_allowed(
    user_id: str,
    *,
    role: str = "user",
    fixture_id: int | None = None,
) -> QuotaCheckResult:
    result = get_user_quota_status(user_id, role=role, fixture_id=fixture_id)
    if not result.allowed:
        raise SubscriptionQuotaError(
            result.message or "Monthly prediction limit reached.",
            limit=result.monthly_limit,
            used=result.used_this_period,
        )
    return result


def record_prediction_usage(user_id: str, fixture_id: int) -> None:
    """Record usage only after a successful pipeline run."""
    _, anchor = _resolve_subscription(user_id)
    store = PredictionUsageStore()
    period = store.billing_period(anchor)
    store.record(user_id, fixture_id, period_key=period.key)


def reset_user_quota(user_id: str) -> dict:
    _, anchor = _resolve_subscription(user_id)
    store = PredictionUsageStore()
    period = store.billing_period(anchor)
    deleted = store.reset_period(user_id, period.key)
    return {"period_key": period.key, "deleted": deleted}


def get_user_usage_detail(user_id: str) -> dict:
    plan_enum, anchor = _resolve_subscription(user_id)
    plan = normalize_plan(plan_enum)
    store = PredictionUsageStore()
    period = store.billing_period(anchor)
    used = store.count_period(user_id, period.key)
    limit = monthly_limit_for_plan(plan)
    return {
        "plan": plan,
        "monthly_limit": limit,
        "used_this_period": used,
        "remaining": max(0, limit - used),
        "period_key": period.key,
        "period_start": period.start.isoformat(),
        "period_end": period.end.isoformat(),
        "fixtures": store.list_period_usage(user_id, period.key),
    }
