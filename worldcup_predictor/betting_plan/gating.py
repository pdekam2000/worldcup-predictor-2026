"""Subscription display gating for betting plan — Phase A17 (no billing changes)."""

from __future__ import annotations

from typing import Any


def _plan_rank(plan: str) -> int:
    p = (plan or "free").lower()
    if p in ("owner", "admin", "super_admin"):
        return 4
    if p in ("pro", "enterprise", "elite"):
        return 3
    if p in ("starter", "basic"):
        return 2
    return 1


def resolve_plan(role: str | None, subscription_plan: str | None = None) -> str:
    r = (role or "").lower()
    if r in ("owner", "admin", "super_admin"):
        return "owner"
    if subscription_plan:
        return subscription_plan.lower()
    return "free"


def gate_betting_plan(plan_doc: dict[str, Any], *, plan: str) -> dict[str, Any]:
    rank = _plan_rank(plan)
    out = dict(plan_doc)

    if rank >= 4:
        return out

    if rank >= 3:
        # Pro — full access, strip only raw score_inputs unless needed
        for key in ("days",):
            days = out.get(key)
            if isinstance(days, dict):
                for day_data in days.values():
                    if isinstance(day_data, dict):
                        for cat in (day_data.get("singles") or {}).values():
                            if isinstance(cat, list):
                                for item in cat:
                                    item.pop("score_inputs", None)
        return out

    if rank >= 2:
        # Starter
        out.pop("portfolios", None)
        days = out.get("days") or {}
        for dk, day in days.items():
            if not isinstance(day, dict):
                continue
            combos = day.get("combos") or {}
            day["combos"] = {k: combos[k] for k in ("safe", "balanced") if k in combos}
            for combo in day["combos"].values():
                for leg in combo.get("legs") or []:
                    leg.pop("score_inputs", None)
        return out

    # Free
    out.pop("portfolios", None)
    out.pop("bankroll", None)
    out.pop("performance_insights", None)
    days = out.get("days") or {}
    for dk, day in days.items():
        if not isinstance(day, dict):
            continue
        singles = day.get("singles") or {}
        best = None
        for cat in ("elite", "strong", "good", "risky"):
            items = singles.get(cat) or []
            if items:
                best = items[0]
                break
        day["singles"] = {"best_single": [best]} if best else {}
        day["singles_preview_only"] = True
        combos = day.get("combos") or {}
        preview = {}
        for k in ("safe", "balanced"):
            c = combos.get(k)
            if c and c.get("legs"):
                preview[k] = {
                    "label": c.get("label"),
                    "leg_count": c.get("leg_count"),
                    "combined_quality": c.get("combined_quality"),
                    "preview_only": True,
                    "legs_hidden": True,
                }
        day["combos"] = preview
        for leg in day.get("avoid") or []:
            leg.pop("score_inputs", None)
    return out
