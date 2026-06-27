"""Paper betting subscription display gating — Phase A18 (no billing changes)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.paper_betting.constants import FREE_DAILY_BET_LIMIT


def plan_rank(plan: str) -> int:
    p = (plan or "free").lower()
    if p in ("owner", "admin", "super_admin"):
        return 4
    if p in ("pro", "enterprise", "elite"):
        return 3
    if p in ("starter", "basic"):
        return 2
    return 1


def can_place_bet(plan: str, bets_today: int) -> tuple[bool, str | None]:
    if plan_rank(plan) >= 2:
        return True, None
    if bets_today >= FREE_DAILY_BET_LIMIT:
        return False, f"Free plan limited to {FREE_DAILY_BET_LIMIT} paper bets per day"
    return True, None


def gate_summary_response(data: dict[str, Any], plan: str) -> dict[str, Any]:
    rank = plan_rank(plan)
    out = dict(data)
    if rank >= 3:
        return out
    if rank >= 2:
        out.pop("strategy_comparison", None)
        return out
    # free — basic only
    for key in ("best_market", "worst_market", "best_combo_type", "average_quality"):
        pass  # keep basic summary fields
    return out


def gate_monthly_report(report: dict[str, Any], plan: str) -> dict[str, Any] | None:
    if plan_rank(plan) < 2:
        return {
            "available": False,
            "message": "Monthly report available on Starter plan and above.",
        }
    return report


def gate_strategy_comparison(data: dict[str, Any], plan: str) -> dict[str, Any]:
    if plan_rank(plan) < 3:
        return {
            "available": False,
            "message": "Strategy comparison available on Pro plan.",
        }
    return data
