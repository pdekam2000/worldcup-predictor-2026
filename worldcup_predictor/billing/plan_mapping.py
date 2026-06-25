"""Phase 39B-3 — Stripe price ID ↔ plan mapping (server-side only)."""

from __future__ import annotations

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.enums import SubscriptionPlan


def price_id_to_plan(price_id: str | None, settings: Settings | None = None) -> SubscriptionPlan | None:
    s = settings or get_settings()
    pid = str(price_id or "").strip()
    if not pid:
        return None
    starter = s.stripe_starter_price_id.strip()
    pro = s.stripe_pro_price_id.strip()
    if starter and pid == starter:
        return SubscriptionPlan.STARTER
    if pro and pid == pro:
        return SubscriptionPlan.PRO
    return None


def plan_monthly_amount(plan: SubscriptionPlan) -> float | None:
    if plan == SubscriptionPlan.STARTER:
        return 5.0
    if plan == SubscriptionPlan.PRO:
        return 19.0
    return None
