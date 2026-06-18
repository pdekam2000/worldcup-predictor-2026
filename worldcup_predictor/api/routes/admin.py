"""Admin foundation routes — user list, stats, system health."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from worldcup_predictor.api.deps import require_admin_user
from worldcup_predictor.api.saas_serializers import parse_uuid, subscription_to_dict, user_admin_to_dict
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.database.postgres.enums import SubscriptionPlan, UserRole
from worldcup_predictor.database.postgres.models import Subscription, User
from worldcup_predictor.database.postgres.session import ping_postgres
from worldcup_predictor.database.saas_factory import saas_uow

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminRolePatchRequest(BaseModel):
    role: str = Field(..., pattern="^(user|admin)$")


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


@router.get("/stats")
def admin_stats(_admin: WebAuthUser = Depends(require_admin_user)) -> dict[str, Any]:
    with saas_uow() as uow:
        session = uow.session
        total_users = int(session.scalar(select(func.count()).select_from(User)) or 0)
        paid_users = int(
            session.scalar(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.plan != SubscriptionPlan.FREE)
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
    with saas_uow() as uow:
        rows = uow.users.list_users(limit=limit, offset=offset)
        items: list[dict[str, Any]] = []
        needle = search.strip().lower()
        for row in rows:
            sub = uow.subscriptions.get_for_user(row.id)
            plan = sub.plan.value if sub else "free"
            entry = user_admin_to_dict(row, plan=plan)
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
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    try:
        uid = parse_uuid(user_id, field="user id")
        role = UserRole(body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with saas_uow() as uow:
        updated = uow.users.set_role(uid, role)
        if updated is None:
            raise HTTPException(status_code=404, detail="User not found")
        sub = uow.subscriptions.get_for_user(updated.id)
        return {
            "status": "ok",
            "user": user_admin_to_dict(updated, plan=sub.plan.value if sub else "free"),
        }


@router.patch("/users/{user_id}/subscription")
def admin_set_user_plan(
    user_id: str,
    plan: str = Query(..., pattern="^(free|pro|elite|unlimited)$"),
    _admin: WebAuthUser = Depends(require_admin_user),
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
