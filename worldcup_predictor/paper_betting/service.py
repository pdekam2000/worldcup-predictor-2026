"""Paper betting service layer — Phase A18."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.betting_plan.bankroll import recommend_stake
from worldcup_predictor.paper_betting.analytics import (
    build_monthly_report,
    build_strategy_comparison,
    build_summary,
)
from worldcup_predictor.paper_betting.constants import BET_STATUS_PENDING, FREE_DAILY_BET_LIMIT
from worldcup_predictor.paper_betting.gating import (
    can_place_bet,
    gate_monthly_report,
    gate_strategy_comparison,
    gate_summary_response,
)
from worldcup_predictor.paper_betting.settlement import settle_pending_bets
from worldcup_predictor.paper_betting.store import PaperBettingStore, _current_month, _utc_now


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def create_or_update_account(
    user_id: str,
    *,
    starting_bankroll: float,
    currency: str = "EUR",
    risk_profile: str = "balanced",
    reset_month: bool = False,
    plan: str = "free",
) -> dict[str, Any]:
    store = PaperBettingStore()
    if reset_month:
        account = store.reset_account_month(
            user_id,
            starting_bankroll=starting_bankroll,
            currency=currency,
            risk_profile=risk_profile,
        )
    else:
        existing = store.get_account(user_id)
        if existing:
            account = store.upsert_account(
                user_id,
                starting_bankroll=starting_bankroll,
                current_bankroll=float(existing["current_bankroll"]),
                currency=currency,
                risk_profile=risk_profile,
            )
        else:
            account = store.upsert_account(
                user_id,
                starting_bankroll=starting_bankroll,
                current_bankroll=starting_bankroll,
                currency=currency,
                risk_profile=risk_profile,
            )
    return {"status": "ok", "account": account, "plan": plan}


def get_account(user_id: str) -> dict[str, Any]:
    store = PaperBettingStore()
    account = store.get_account(user_id)
    if not account:
        return {"status": "ok", "account": None, "month": _current_month()}
    return {"status": "ok", "account": account, "month": account.get("month")}


def place_bet(
    user_id: str,
    *,
    fixture_id: int,
    market: str,
    prediction: str,
    stake: float | None = None,
    odds_decimal: float | None = None,
    odds_estimated: bool = False,
    bet_quality_score: float | None = None,
    combo_type: str | None = None,
    combo_group_id: str | None = None,
    source_page: str | None = None,
    snapshot_id: str | None = None,
    competition_key: str | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
    plan: str = "free",
) -> dict[str, Any]:
    store = PaperBettingStore()
    ok, reason = can_place_bet(plan, store.count_bets_today(user_id))
    if not ok:
        return {"status": "error", "code": "daily_limit", "message": reason}

    account = store.get_account(user_id)
    if not account:
        return {"status": "error", "code": "no_account", "message": "Create a virtual bankroll first."}

    balance = float(account["current_bankroll"])
    q = float(bet_quality_score or 50)
    if stake is None:
        rec = recommend_stake(
            balance,
            profile=account.get("risk_profile") or "balanced",
            bet_quality_score=q,
            is_combo=bool(combo_group_id),
        )
        stake = float(rec["recommended_stake"])
    stake = round(float(stake), 2)
    if stake <= 0:
        return {"status": "error", "code": "invalid_stake", "message": "Stake must be positive."}
    if stake > balance:
        return {"status": "error", "code": "insufficient_bankroll", "message": "Insufficient virtual bankroll."}

    bet_id = store.insert_bet(
        {
            "user_id": user_id,
            "account_id": int(account["id"]),
            "fixture_id": int(fixture_id),
            "competition_key": competition_key,
            "home_team": home_team,
            "away_team": away_team,
            "market": market,
            "prediction": prediction,
            "stake": stake,
            "odds_decimal": odds_decimal,
            "odds_estimated": 1 if odds_estimated else 0,
            "bet_quality_score": bet_quality_score,
            "combo_type": combo_type,
            "combo_group_id": combo_group_id,
            "source_page": source_page,
            "snapshot_id": snapshot_id,
            "status": BET_STATUS_PENDING,
            "created_at": _utc_now(),
        }
    )
    store.update_bankroll(int(account["id"]), round(balance - stake, 2))
    return {"status": "ok", "bet_id": bet_id, "stake": stake}


def place_combo_bets(
    user_id: str,
    *,
    legs: list[dict[str, Any]],
    combo_type: str,
    source_page: str | None = None,
    plan: str = "free",
) -> dict[str, Any]:
    group_id = str(uuid.uuid4())
    placed = []
    for leg in legs:
        result = place_bet(
            user_id,
            fixture_id=int(leg["fixture_id"]),
            market=str(leg.get("market") or "1x2"),
            prediction=str(leg.get("prediction") or leg.get("selection") or ""),
            stake=leg.get("stake"),
            odds_decimal=leg.get("odds_decimal"),
            odds_estimated=bool(leg.get("odds_estimated")),
            bet_quality_score=leg.get("bet_quality_score"),
            combo_type=combo_type,
            combo_group_id=group_id,
            source_page=source_page,
            snapshot_id=leg.get("snapshot_id"),
            competition_key=leg.get("competition_key"),
            home_team=leg.get("home_team"),
            away_team=leg.get("away_team"),
            plan=plan,
        )
        if result.get("status") != "ok":
            return result
        placed.append(result)
    return {"status": "ok", "combo_group_id": group_id, "bets": placed}


def list_bets(user_id: str, *, status: str | None = None) -> dict[str, Any]:
    store = PaperBettingStore()
    return {"status": "ok", "bets": store.list_bets(user_id, status=status)}


def get_summary(user_id: str, *, period: str = "all", plan: str = "free") -> dict[str, Any]:
    store = PaperBettingStore()
    settle_pending_bets(store=store, user_id=user_id)
    summary = build_summary(store, user_id, period=period)
    return gate_summary_response({"status": "ok", **summary}, plan)


def get_monthly_report(user_id: str, *, month: str | None = None, plan: str = "free") -> dict[str, Any]:
    store = PaperBettingStore()
    report = build_monthly_report(store, user_id, month=month)
    gated = gate_monthly_report(report, plan)
    return {"status": "ok", "report": gated}


def get_strategy_comparison(user_id: str, *, bankroll: float = 100.0, plan: str = "free") -> dict[str, Any]:
    store = PaperBettingStore()
    data = build_strategy_comparison(store, user_id, bankroll=bankroll)
    return {"status": "ok", **gate_strategy_comparison(data, plan)}


def reset_account_month(
    user_id: str,
    *,
    starting_bankroll: float,
    currency: str = "EUR",
    risk_profile: str = "balanced",
) -> dict[str, Any]:
    store = PaperBettingStore()
    account = store.reset_account_month(
        user_id,
        starting_bankroll=starting_bankroll,
        currency=currency,
        risk_profile=risk_profile,
    )
    return {"status": "ok", "account": account}
