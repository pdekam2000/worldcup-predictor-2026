"""Betting plan read APIs — Phase A17."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from worldcup_predictor.api.deps import get_optional_current_user, user_has_owner_access
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.betting_plan.engine import (
    build_combo_plan,
    build_daily_betting_plan,
    build_portfolio_plan,
)
from worldcup_predictor.betting_plan.gating import resolve_plan  # noqa: F401 — re-export for tests

router = APIRouter(prefix="/betting-plan", tags=["betting-plan"])

ComboType = Literal["safe", "balanced", "value", "high_odds"]
RiskProfile = Literal["conservative", "balanced", "aggressive"]


def _user_plan(user: WebAuthUser | None) -> str:
    if user and user_has_owner_access(user.role):
        return "owner"
    if not user:
        return "free"
    try:
        from worldcup_predictor.subscription.quota_service import _resolve_subscription
        from worldcup_predictor.subscription.plan_limits import normalize_plan

        plan_enum, _ = _resolve_subscription(user.id)
        return normalize_plan(plan_enum)
    except Exception:
        return "free"


def _include_debug(user: WebAuthUser | None) -> bool:
    if not user:
        return False
    return user_has_owner_access(user.role) or user.role in ("admin", "super_admin")


@router.get("/today")
def betting_plan_today(
    bankroll: float | None = Query(default=None, ge=0),
    profile: RiskProfile = Query(default="balanced"),
    user: WebAuthUser | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    plan = _user_plan(user)
    return build_daily_betting_plan(
        plan_date=None,
        include_tomorrow=True,
        include_debug=_include_debug(user),
        plan=plan,
        bankroll=bankroll,
        risk_profile=profile,
    )


@router.get("/date")
def betting_plan_date(
    date: str = Query(..., description="YYYY-MM-DD or today/tomorrow"),
    bankroll: float | None = Query(default=None, ge=0),
    profile: RiskProfile = Query(default="balanced"),
    user: WebAuthUser | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    plan = _user_plan(user)
    return build_daily_betting_plan(
        plan_date=date,
        include_tomorrow=False,
        include_debug=_include_debug(user),
        plan=plan,
        bankroll=bankroll,
        risk_profile=profile,
    )


@router.get("/portfolio")
def betting_plan_portfolio(
    date: str = Query(default="today"),
    bankroll: float = Query(default=100.0, ge=1),
    profile: RiskProfile = Query(default="balanced"),
    user: WebAuthUser | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    plan = _user_plan(user)
    return build_portfolio_plan(
        plan_date=date,
        bankroll=bankroll,
        profile=profile,
        include_debug=_include_debug(user),
        plan=plan,
    )


@router.get("/combo")
def betting_plan_combo(
    date: str = Query(default="today"),
    type: ComboType = Query(default="safe", alias="type"),
    user: WebAuthUser | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    plan = _user_plan(user)
    return build_combo_plan(
        plan_date=date,
        combo_type=type,
        include_debug=_include_debug(user),
        plan=plan,
    )
