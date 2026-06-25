"""Subscription plan limits and market access — Phase 38A."""

from __future__ import annotations

from worldcup_predictor.database.postgres.enums import SubscriptionPlan

# Legacy Phase 34 daily limits (regression scripts only)
PLAN_DAILY_PREDICTION_LIMITS: dict[SubscriptionPlan, int | None] = {
    SubscriptionPlan.FREE: 1,
    SubscriptionPlan.STARTER: None,
    SubscriptionPlan.PRO: None,
    SubscriptionPlan.ELITE: None,
    SubscriptionPlan.UNLIMITED: None,
}

PLAN_MONTHLY_PREDICTION_LIMITS: dict[str, int] = {
    "free": 4,
    "starter": 28,
    "pro": 60,
}

PLAN_PRICES_EUR: dict[str, int] = {
    "free": 0,
    "starter": 5,
    "pro": 19,
}

PLAN_MARKETS: dict[str, frozenset[str] | str] = {
    "free": frozenset({"1x2"}),
    "starter": frozenset({"1x2", "btts", "over_under"}),
    "pro": "all",
}

_PRO_FEATURES: dict[str, object] = {
    "monthly_predictions": 60,
    "markets": "all",
    "btts": True,
    "over_under": True,
    "goal_minute": True,
    "premium_markets": True,
    "full_history": True,
    "ranked_picks": True,
}

PLAN_FEATURES: dict[str, dict[str, object]] = {
    "free": {
        "monthly_predictions": 4,
        "markets": ["1X2"],
        "btts": False,
        "over_under": False,
        "goal_minute": False,
        "premium_markets": False,
        "full_history": False,
        "ranked_picks": False,
    },
    "starter": {
        "monthly_predictions": 28,
        "markets": ["1X2", "BTTS", "Over/Under"],
        "btts": True,
        "over_under": True,
        "goal_minute": False,
        "premium_markets": False,
        "full_history": True,
        "ranked_picks": True,
    },
    "pro": dict(_PRO_FEATURES),
    "elite": dict(_PRO_FEATURES),
    "unlimited": dict(_PRO_FEATURES),
}


def normalize_plan(plan: str | SubscriptionPlan | None) -> str:
    raw = plan.value if isinstance(plan, SubscriptionPlan) else str(plan or "free").lower()
    if raw in ("elite", "unlimited"):
        return "pro"
    if raw in PLAN_MONTHLY_PREDICTION_LIMITS:
        return raw
    return "free"


def monthly_limit_for_plan(plan: str | SubscriptionPlan | None) -> int:
    return PLAN_MONTHLY_PREDICTION_LIMITS[normalize_plan(plan)]


def plan_allows_all_markets(plan: str | SubscriptionPlan | None) -> bool:
    markets = PLAN_MARKETS.get(normalize_plan(plan), frozenset({"1x2"}))
    return markets == "all"


def plan_allowed_market_keys(plan: str | SubscriptionPlan | None) -> frozenset[str] | None:
    markets = PLAN_MARKETS.get(normalize_plan(plan), frozenset({"1x2"}))
    if markets == "all":
        return None
    return markets  # type: ignore[return-value]
