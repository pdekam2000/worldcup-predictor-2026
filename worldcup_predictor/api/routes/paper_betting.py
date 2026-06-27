"""Paper betting simulator APIs — Phase A18."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from worldcup_predictor.api.deps import get_current_user, require_admin_user, user_has_owner_access
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.paper_betting.service import (
    create_or_update_account,
    get_account,
    get_monthly_report,
    get_strategy_comparison,
    get_summary,
    list_bets,
    place_bet,
    place_combo_bets,
    reset_account_month,
)
from worldcup_predictor.paper_betting.settlement import settle_pending_bets
from worldcup_predictor.paper_betting.store import PaperBettingStore

router = APIRouter(prefix="/paper-betting", tags=["paper-betting"])

RiskProfile = Literal["conservative", "balanced", "aggressive"]
Period = Literal["today", "week", "month", "all"]


def _user_plan(user: WebAuthUser) -> str:
    if user_has_owner_access(user.role):
        return "owner"
    try:
        from worldcup_predictor.subscription.quota_service import _resolve_subscription
        from worldcup_predictor.subscription.plan_limits import normalize_plan

        plan_enum, _ = _resolve_subscription(user.id)
        return normalize_plan(plan_enum)
    except Exception:
        return "free"


class AccountBody(BaseModel):
    starting_bankroll: float = Field(..., gt=0, le=1_000_000)
    currency: str = Field(default="EUR", max_length=8)
    risk_profile: RiskProfile = "balanced"
    reset_month: bool = False


class BetBody(BaseModel):
    fixture_id: int = Field(..., ge=1)
    market: str = Field(..., min_length=1, max_length=64)
    prediction: str = Field(..., min_length=1, max_length=128)
    stake: float | None = Field(default=None, gt=0)
    odds_decimal: float | None = Field(default=None, gt=1)
    odds_estimated: bool = False
    bet_quality_score: float | None = Field(default=None, ge=0, le=100)
    combo_type: str | None = None
    source_page: str | None = None
    snapshot_id: str | None = None
    competition_key: str | None = None
    home_team: str | None = None
    away_team: str | None = None


class ComboBetBody(BaseModel):
    combo_type: str = Field(default="balanced")
    source_page: str | None = None
    legs: list[dict[str, Any]] = Field(..., min_length=2, max_length=8)


@router.post("/account")
def paper_account_create(
    body: AccountBody,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return create_or_update_account(
        user.id,
        starting_bankroll=body.starting_bankroll,
        currency=body.currency,
        risk_profile=body.risk_profile,
        reset_month=body.reset_month,
        plan=_user_plan(user),
    )


@router.get("/account")
def paper_account_get(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    return get_account(user.id)


@router.post("/bets")
def paper_bet_create(
    body: BetBody,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    result = place_bet(
        user.id,
        fixture_id=body.fixture_id,
        market=body.market,
        prediction=body.prediction,
        stake=body.stake,
        odds_decimal=body.odds_decimal,
        odds_estimated=body.odds_estimated,
        bet_quality_score=body.bet_quality_score,
        combo_type=body.combo_type,
        source_page=body.source_page,
        snapshot_id=body.snapshot_id,
        competition_key=body.competition_key,
        home_team=body.home_team,
        away_team=body.away_team,
        plan=_user_plan(user),
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/bets/combo")
def paper_combo_create(
    body: ComboBetBody,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    result = place_combo_bets(
        user.id,
        legs=body.legs,
        combo_type=body.combo_type,
        source_page=body.source_page,
        plan=_user_plan(user),
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/bets")
def paper_bets_list(
    status: str | None = Query(default=None),
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return list_bets(user.id, status=status)


@router.get("/summary")
def paper_summary(
    period: Period = Query(default="all"),
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return get_summary(user.id, period=period, plan=_user_plan(user))


@router.post("/settle")
def paper_settle_user(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    return settle_pending_bets(user_id=user.id)


@router.get("/monthly-report")
def paper_monthly_report(
    month: str | None = Query(default=None),
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return get_monthly_report(user.id, month=month, plan=_user_plan(user))


@router.get("/strategy-comparison")
def paper_strategy_comparison(
    bankroll: float = Query(default=100.0, ge=1),
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return get_strategy_comparison(user.id, bankroll=bankroll, plan=_user_plan(user))


@router.post("/account/reset")
def paper_account_reset(
    body: AccountBody,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return reset_account_month(
        user.id,
        starting_bankroll=body.starting_bankroll,
        currency=body.currency,
        risk_profile=body.risk_profile,
    )


admin_router = APIRouter(prefix="/admin/paper-betting", tags=["admin-paper-betting"])


@admin_router.post("/settle-pending")
def admin_settle_pending(
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    return settle_pending_bets()


@admin_router.get("/aggregate")
def admin_paper_aggregate(
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    store = PaperBettingStore()
    return {"status": "ok", "aggregate": store.admin_aggregate()}
