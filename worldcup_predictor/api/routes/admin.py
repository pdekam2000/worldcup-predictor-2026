"""Admin foundation routes — user list, stats, system health."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from worldcup_predictor.api.deps import require_admin_user, require_super_admin_user
from worldcup_predictor.api.saas_serializers import parse_uuid, subscription_to_dict, user_admin_to_dict
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.database.postgres.enums import SubscriptionPlan, UserRole
from worldcup_predictor.database.postgres.models import Subscription, User
from worldcup_predictor.database.postgres.session import ping_postgres
from worldcup_predictor.database.saas_factory import saas_uow
from worldcup_predictor.quota.quota_guard import quota_risk_level
from worldcup_predictor.quota.quota_tracker import get_quota_tracker

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminRolePatchRequest(BaseModel):
    role: str = Field(..., pattern="^(user|admin|super_admin)$")
    confirm_self: bool = False


class AdminBanRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    confirm_self: bool = False


@router.get("/health")
def admin_health(_admin: WebAuthUser = Depends(require_admin_user)) -> dict[str, Any]:
    postgres_ok = ping_postgres()
    return {
        "status": "ok" if postgres_ok else "degraded",
        "services": [
            {"name": "Prediction Engine", "status": "operational", "uptime": "n/a"},
            {"name": "Match Data API", "status": "operational", "uptime": "n/a"},
            {"name": "User Auth Service", "status": "operational", "uptime": "n/a"},
            {
                "name": "PostgreSQL SaaS DB",
                "status": "operational" if postgres_ok else "down",
                "uptime": "n/a",
            },
            {"name": "Notification Service", "status": "operational", "uptime": "n/a"},
        ],
    }


@router.get("/quota")
def admin_quota(_admin: WebAuthUser = Depends(require_admin_user)) -> dict[str, Any]:
    snap = get_quota_tracker().snapshot()
    risk = quota_risk_level()
    db_stats = None
    try:
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        db_stats = FootballIntelligenceRepository().get_api_quota_stats(snap.stat_date)
    except Exception:
        db_stats = None

    provider_live = dict(snap.provider_live)
    if not provider_live and snap.live_requests:
        provider_live = {"api_football": snap.live_requests}

    return {
        "status": "ok",
        "stat_date": snap.stat_date,
        "api_calls_today": snap.live_requests,
        "api_calls_by_provider": provider_live,
        "cache_hits": snap.cache_hits,
        "cache_misses": snap.prediction_cache_misses,
        "local_hits": snap.local_hits,
        "prediction_cache_hits": snap.prediction_cache_hits,
        "prediction_cache_misses": snap.prediction_cache_misses,
        "calls_saved": snap.calls_saved,
        "cache_hit_rate": snap.cache_hit_rate,
        "rate_limit_retries": snap.rate_limit_retries,
        "quota_risk": risk,
        "persisted": db_stats,
    }


@router.get("/stats")
def admin_stats(_admin: WebAuthUser = Depends(require_admin_user)) -> dict[str, Any]:
    with saas_uow() as uow:
        session = uow.session
        total_users = int(session.scalar(select(func.count()).select_from(User)) or 0)
        paid_users = int(
            session.scalar(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.plan.not_in([SubscriptionPlan.FREE]))
            )
            or 0
        )
        return {
            "status": "ok",
            "total_users": total_users,
            "paid_subscribers": paid_users,
            "predictions_today": 0,
            "system_uptime": "n/a",
        }


@router.get("/users")
def admin_users(
    search: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    from worldcup_predictor.subscription.quota_service import get_user_usage_detail

    with saas_uow() as uow:
        rows = uow.users.list_users(limit=limit, offset=offset)
        items: list[dict[str, Any]] = []
        needle = search.strip().lower()
        for row in rows:
            sub = uow.subscriptions.get_for_user(row.id)
            plan = sub.plan.value if sub else "free"
            usage = get_user_usage_detail(str(row.id))
            entry = user_admin_to_dict(
                row,
                plan=plan,
                predictions_used_month=int(usage.get("used_this_period") or 0),
            )
            if needle:
                hay = f"{entry['full_name']} {entry['email']}".lower()
                if needle not in hay:
                    continue
            items.append(entry)
        return {"status": "ok", "users": items}


@router.patch("/users/{user_id}/role")
def admin_set_user_role(
    user_id: str,
    body: AdminRolePatchRequest,
    admin: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    from worldcup_predictor.auth.user_management import UserManagementError, audit_user_event, validate_role_change

    try:
        uid = parse_uuid(user_id, field="user id")
        role = UserRole(body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with saas_uow() as uow:
        target = uow.users.get_by_id(uid)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        try:
            validate_role_change(
                actor_id=admin.id,
                target=target,
                new_role=role,
                confirm_self=body.confirm_self,
            )
        except UserManagementError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        updated = uow.users.set_role(uid, role)
        if updated is None:
            raise HTTPException(status_code=404, detail="User not found")
        uow.users.bump_token_version(uid)
        event = "user_promoted" if role in (UserRole.ADMIN, UserRole.SUPER_ADMIN) else "user_demoted"
        audit_user_event(event, actor_id=admin.id, target_id=str(uid), detail=f"role={role.value}")
        sub = uow.subscriptions.get_for_user(updated.id)
        return {
            "status": "ok",
            "user": user_admin_to_dict(updated, plan=sub.plan.value if sub else "free"),
        }


@router.patch("/users/{user_id}/subscription")
def admin_set_user_plan(
    user_id: str,
    plan: str = Query(..., pattern="^(free|starter|pro|elite|unlimited)$"),
    _admin: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    try:
        uid = parse_uuid(user_id, field="user id")
        sub_plan = SubscriptionPlan(plan)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with saas_uow() as uow:
        user = uow.users.get_by_id(uid)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        record = uow.subscriptions.upsert(uid, plan=sub_plan)
        return {"status": "ok", "subscription": subscription_to_dict(record)}


@router.get("/users/{user_id}/billing")
def admin_user_billing(
    user_id: str,
    _admin: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    try:
        uid = parse_uuid(user_id, field="user id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with saas_uow() as uow:
        if uow.users.get_by_id(uid) is None:
            raise HTTPException(status_code=404, detail="User not found")

    from worldcup_predictor.billing.billing_service import get_billing_service

    return get_billing_service().get_admin_billing_summary(str(uid))


@router.get("/users/{user_id}/usage")
def admin_user_usage(
    user_id: str,
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    try:
        uid = parse_uuid(user_id, field="user id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with saas_uow() as uow:
        user = uow.users.get_by_id(uid)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

    from worldcup_predictor.subscription.quota_service import get_user_usage_detail

    return {"status": "ok", "usage": get_user_usage_detail(str(uid))}


@router.post("/users/{user_id}/quota/reset")
def admin_reset_user_quota(
    user_id: str,
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    try:
        uid = parse_uuid(user_id, field="user id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with saas_uow() as uow:
        user = uow.users.get_by_id(uid)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

    from worldcup_predictor.subscription.contact_admin import write_subscription_audit
    from worldcup_predictor.subscription.quota_service import reset_user_quota

    result = reset_user_quota(str(uid))
    write_subscription_audit("admin_quota_reset", user_id=str(uid), detail=f"deleted={result['deleted']}")
    return {"status": "ok", **result}


@router.post("/users/{user_id}/ban")
def admin_ban_user(
    user_id: str,
    body: AdminBanRequest,
    admin: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    from worldcup_predictor.auth.user_management import UserManagementError, audit_user_event, validate_ban

    try:
        uid = parse_uuid(user_id, field="user id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with saas_uow() as uow:
        target = uow.users.get_by_id(uid)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        try:
            validate_ban(actor_id=admin.id, target=target, confirm_self=body.confirm_self)
        except UserManagementError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        updated = uow.users.set_banned(uid, reason=body.reason)
        uow.users.bump_token_version(uid)
        audit_user_event("user_banned", actor_id=admin.id, target_id=str(uid), detail=body.reason)
        sub = uow.subscriptions.get_for_user(uid)
        return {
            "status": "ok",
            "user": user_admin_to_dict(updated, plan=sub.plan.value if sub else "free") if updated else None,
        }


@router.post("/users/{user_id}/unban")
def admin_unban_user(
    user_id: str,
    admin: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    from worldcup_predictor.auth.user_management import audit_user_event

    try:
        uid = parse_uuid(user_id, field="user id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with saas_uow() as uow:
        updated = uow.users.clear_ban(uid)
        if updated is None:
            raise HTTPException(status_code=404, detail="User not found")
        audit_user_event("user_unbanned", actor_id=admin.id, target_id=str(uid))
        sub = uow.subscriptions.get_for_user(uid)
        return {
            "status": "ok",
            "user": user_admin_to_dict(updated, plan=sub.plan.value if sub else "free"),
        }


@router.post("/users/{user_id}/kick")
def admin_kick_user(
    user_id: str,
    admin: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    from worldcup_predictor.auth.user_management import audit_user_event

    try:
        uid = parse_uuid(user_id, field="user id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with saas_uow() as uow:
        target = uow.users.get_by_id(uid)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        if str(target.id) == admin.id:
            raise HTTPException(status_code=409, detail="Cannot kick your own session.")
        new_tv = uow.users.bump_token_version(uid)
        audit_user_event("user_kicked", actor_id=admin.id, target_id=str(uid), detail=f"token_version={new_tv}")
        return {"status": "ok", "token_version": new_tv}


@router.get("/email/diagnostics")
def admin_email_diagnostics(
    _admin: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    from worldcup_predictor.notifications.diagnostics import email_diagnostics

    return {"status": "ok", "email": email_diagnostics()}


@router.get("/commercial/analytics")
def admin_commercial_analytics(
    _admin: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    from worldcup_predictor.subscription.commercial_analytics import build_commercial_analytics

    return {"status": "ok", "analytics": build_commercial_analytics()}


@router.get("/commercial/readiness")
def admin_commercial_readiness(
    _admin: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    from worldcup_predictor.subscription.commercial_readiness import run_commercial_readiness_audit

    return {"status": "ok", **run_commercial_readiness_audit()}
