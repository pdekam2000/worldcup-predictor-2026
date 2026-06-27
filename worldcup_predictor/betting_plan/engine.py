"""Daily betting plan engine — Phase A17."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from worldcup_predictor.betting_plan.bankroll import attach_stakes, portfolio_exposure, recommend_stake
from worldcup_predictor.betting_plan.combos import build_all_combos, build_combo
from worldcup_predictor.betting_plan.constants import SINGLE_CATEGORIES
from worldcup_predictor.betting_plan.day_quality import assess_day_quality
from worldcup_predictor.betting_plan.gating import gate_betting_plan
from worldcup_predictor.betting_plan.legs import collect_legs_for_date, parse_plan_date
from worldcup_predictor.betting_plan.performance_insights import build_performance_insights
from worldcup_predictor.config.settings import Settings, get_settings


def _categorize_singles(legs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    seen: set[tuple[int, str]] = set()
    unique: list[dict[str, Any]] = []
    for leg in legs:
        key = (int(leg["fixture_id"]), str(leg.get("market")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(leg)

    out: dict[str, list[dict[str, Any]]] = {cat: [] for cat, _, _ in SINGLE_CATEGORIES}
    for leg in unique:
        score = float(leg.get("bet_quality_score") or 0)
        placed = False
        for cat, lo, hi in SINGLE_CATEGORIES:
            if score >= lo and (hi is None or score <= hi):
                out[cat].append(leg)
                placed = True
                break
        if not placed:
            out["avoid"].append(leg)
    return out


def _plan_for_day(
    plan_date: date,
    *,
    settings: Settings | None,
    include_debug: bool,
) -> dict[str, Any]:
    legs = collect_legs_for_date(plan_date, settings=settings, include_debug=include_debug)
    singles = _categorize_singles(legs)
    combos = build_all_combos(legs)
    day_q = assess_day_quality(legs, combos)
    best_singles = (
        singles.get("elite", [])[:5]
        + singles.get("strong", [])[:5]
        + singles.get("good", [])[:3]
    )[:8]

    return {
        "date": plan_date.isoformat(),
        "day_quality": day_q,
        "best_single_bets": best_singles,
        "singles": singles,
        "combos": combos,
        "avoid": singles.get("avoid", []),
        "leg_count": len(legs),
        "generated_at": _utc_now_iso(),
    }


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def build_daily_betting_plan(
    *,
    settings: Settings | None = None,
    plan_date: str | None = None,
    include_tomorrow: bool = True,
    include_debug: bool = False,
    plan: str = "pro",
    bankroll: float | None = None,
    risk_profile: str = "balanced",
) -> dict[str, Any]:
    settings = settings or get_settings()
    today = parse_plan_date("today")
    tomorrow = today + timedelta(days=1)

    if plan_date:
        target = parse_plan_date(plan_date)
        days = {target.isoformat(): _plan_for_day(target, settings=settings, include_debug=include_debug)}
    else:
        days = {today.isoformat(): _plan_for_day(today, settings=settings, include_debug=include_debug)}
        if include_tomorrow:
            days[tomorrow.isoformat()] = _plan_for_day(tomorrow, settings=settings, include_debug=include_debug)

    doc: dict[str, Any] = {
        "status": "ok",
        "version": "phase_a17",
        "days": days,
        "performance_insights": build_performance_insights(settings=settings),
    }

    if bankroll is not None and float(bankroll) > 0:
        doc["bankroll"] = _bankroll_section(
            days,
            bankroll=float(bankroll),
            profile=risk_profile,
        )
        doc["portfolios"] = build_portfolios_internal(
            days,
            bankroll=float(bankroll),
            profile=risk_profile,
        )

    return gate_betting_plan(doc, plan=plan)


def build_combo_plan(
    *,
    plan_date: str | None = None,
    combo_type: str = "safe",
    settings: Settings | None = None,
    include_debug: bool = False,
    plan: str = "pro",
) -> dict[str, Any]:
    settings = settings or get_settings()
    target = parse_plan_date(plan_date)
    legs = collect_legs_for_date(target, settings=settings, include_debug=include_debug)
    combo = build_combo(legs, combo_type)
    doc = {
        "status": "ok",
        "date": target.isoformat(),
        "combo": combo,
        "generated_at": _utc_now_iso(),
    }
    return gate_betting_plan(doc, plan=plan)


def build_portfolio_plan(
    *,
    plan_date: str | None = None,
    bankroll: float = 100.0,
    profile: str = "balanced",
    settings: Settings | None = None,
    include_debug: bool = False,
    plan: str = "pro",
) -> dict[str, Any]:
    settings = settings or get_settings()
    target = parse_plan_date(plan_date)
    day = _plan_for_day(target, settings=settings, include_debug=include_debug)
    portfolios = build_portfolios_internal({target.isoformat(): day}, bankroll=bankroll, profile=profile)
    doc = {
        "status": "ok",
        "date": target.isoformat(),
        "bankroll": bankroll,
        "profile": profile,
        "portfolios": portfolios,
        "generated_at": _utc_now_iso(),
    }
    return gate_betting_plan(doc, plan=plan)


def build_portfolios_internal(
    days: dict[str, dict[str, Any]],
    *,
    bankroll: float,
    profile: str,
) -> dict[str, Any]:
    # Use first day in map
    day = next(iter(days.values()), {})
    singles = day.get("singles") or {}
    combos = day.get("combos") or {}

    def _pack(name: str, single_keys: tuple[str, ...], combo_keys: tuple[str, ...], warning: str | None) -> dict[str, Any]:
        s_items = []
        for k in single_keys:
            s_items.extend((singles.get(k) or [])[:3])
        c_items = []
        for k in combo_keys:
            c = combos.get(k)
            if c and c.get("legs"):
                c_items.append(c)
        s_staked = attach_stakes(s_items, bankroll=bankroll, profile=profile, is_combo=False)
        c_staked = attach_stakes(c_items, bankroll=bankroll, profile=profile, is_combo=True)
        exposure = portfolio_exposure(s_staked, c_staked, bankroll=bankroll)
        return {
            "name": name,
            "singles": s_staked,
            "combos": c_staked,
            "warning": warning,
            **exposure,
        }

    return {
        "conservative": _pack(
            "Conservative Portfolio",
            ("elite",),
            ("safe",),
            None,
        ),
        "balanced": _pack(
            "Balanced Portfolio",
            ("strong", "good"),
            ("safe", "balanced"),
            None,
        ),
        "aggressive": _pack(
            "Aggressive Portfolio",
            ("good", "risky"),
            ("value", "high_odds"),
            "High risk — value and high-odds combos included.",
        ),
    }


def _bankroll_section(
    days: dict[str, dict[str, Any]],
    *,
    bankroll: float,
    profile: str,
) -> dict[str, Any]:
    day = next(iter(days.values()), {})
    best = (day.get("best_single_bets") or [{}])[0] if day.get("best_single_bets") else {}
    q = float(best.get("bet_quality_score") or 50)
    stake = recommend_stake(bankroll, profile=profile, bet_quality_score=q, is_combo=False)
    return {
        "bankroll": bankroll,
        "profile": profile,
        "example_single_stake": stake,
        "risk_warning": stake.get("max_daily_exposure_pct", 0) > 12,
    }
