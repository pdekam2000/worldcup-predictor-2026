"""The Odds API credit guard — quotas, cache, and call eligibility."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings
from worldcup_predictor.domain.fixture import Fixture
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.providers.odds_api_credit.config import (
    compute_odds_api_credits,
    odds_api_cache_hours,
    odds_api_credits_per_call,
    odds_api_daily_hard_limit,
    odds_api_daily_soft_limit,
    odds_api_low_bookmaker_count,
    odds_api_low_sharp_score,
    odds_api_monthly_limit,
)
from worldcup_predictor.providers.odds_api_credit.repository import get_odds_api_repository

DEFAULT_MARKET_KEY = "h2h,totals"


@dataclass
class OddsApiGuardDecision:
    allowed: bool
    reason: str = ""
    from_cache: bool = False
    cached_event: dict[str, Any] | None = None
    daily_used: int = 0
    monthly_used: int = 0
    daily_soft_limit: int = 15
    daily_hard_limit: int = 16
    monthly_limit: int = 500
    skip_logged: bool = False


def usage_summary(settings: Settings | None = None) -> dict[str, int]:
    """Current daily/monthly credit totals."""
    _ = settings
    repo = get_odds_api_repository()
    summary = repo.usage_summary()
    summary["monthly_limit"] = odds_api_monthly_limit()
    summary["daily_soft_limit"] = odds_api_daily_soft_limit()
    summary["daily_hard_limit"] = odds_api_daily_hard_limit()
    summary["monthly_remaining"] = max(0, odds_api_monthly_limit() - summary["monthly_used"])
    summary["daily_remaining"] = max(0, odds_api_daily_hard_limit() - summary["daily_used"])
    return summary


def _cache_fresh(cached_at: str, *, hours: int | None = None) -> bool:
    ttl = hours if hours is not None else odds_api_cache_hours()
    try:
        ts = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - ts < timedelta(hours=ttl)
    except Exception:
        return False


def _needs_external_odds(report: MatchIntelligenceReport) -> tuple[bool, str]:
    odds = report.odds
    if not odds or not odds.available or not odds.bookmakers:
        return True, "api_football_missing"

    if len(odds.bookmakers) < odds_api_low_bookmaker_count():
        return True, "low_bookmaker_count"

    try:
        from worldcup_predictor.odds.sharp_money_intelligence_engine import build_sharp_money_intelligence

        sharp = build_sharp_money_intelligence(report)
        if sharp.sharp_money_score < odds_api_low_sharp_score():
            return True, "low_sharp_confidence"
    except Exception:
        return True, "sharp_eval_unavailable"

    return False, "primary_sufficient"


def evaluate_odds_api_call(
    report: MatchIntelligenceReport,
    fixture: Fixture,
    settings: Settings,
    *,
    force: bool = False,
    market_key: str = DEFAULT_MARKET_KEY,
) -> OddsApiGuardDecision:
    """Decide whether The Odds API may be called for this fixture."""
    repo = get_odds_api_repository()
    daily_used = repo.sum_credits_for_date()
    monthly_used = repo.sum_credits_for_month()
    monthly_limit = odds_api_monthly_limit()
    daily_soft = odds_api_daily_soft_limit()
    daily_hard = odds_api_daily_hard_limit()

    base = OddsApiGuardDecision(
        allowed=False,
        daily_used=daily_used,
        monthly_used=monthly_used,
        daily_soft_limit=daily_soft,
        daily_hard_limit=daily_hard,
        monthly_limit=monthly_limit,
    )

    if not settings.the_odds_api_configured:
        base.reason = "not_configured"
        return base

    if monthly_used >= monthly_limit:
        base.reason = "monthly_limit_exceeded"
        return base

    if daily_used >= daily_hard:
        base.reason = "daily_hard_limit_exceeded"
        return base

    need_reason = "manual_refresh"

    if not force:
        cached = repo.get_cache(fixture.id, market_key)
        if cached and _cache_fresh(cached["cached_at"]):
            try:
                event = json.loads(cached["response_json"])
                if isinstance(event, dict):
                    base.allowed = True
                    base.from_cache = True
                    base.cached_event = event
                    base.reason = "cache_hit"
                    return base
            except json.JSONDecodeError:
                pass

        needs, need_reason = _needs_external_odds(report)
        if not needs:
            base.reason = need_reason
            return base

    credits = compute_odds_api_credits(settings.the_odds_api_regions, DEFAULT_MARKET_KEY)
    if daily_used + credits > daily_hard:
        base.reason = "daily_hard_limit_exceeded"
        return base

    base.allowed = True
    base.reason = need_reason if not force else "manual_refresh"
    if not force and daily_used >= daily_soft:
        base.reason = f"{need_reason}:daily_soft"
    return base


def record_odds_api_call(
    *,
    fixture_id: int | None,
    endpoint: str,
    event: dict[str, Any] | None,
    market_key: str = DEFAULT_MARKET_KEY,
    credits: int | None = None,
    source: str = "live",
    settings: Settings | None = None,
) -> None:
    """Persist usage and cache after a live API call."""
    repo = get_odds_api_repository()
    used = credits
    if used is None and settings is not None:
        used = compute_odds_api_credits(settings.the_odds_api_regions, market_key)
    repo.record_usage(
        endpoint=endpoint,
        fixture_id=fixture_id,
        credits_used=used or odds_api_credits_per_call(),
        source=source,
    )
    if event and fixture_id is not None:
        repo.set_cache(fixture_id, market_key, event)


def attach_guard_metadata(
    report: MatchIntelligenceReport,
    decision: OddsApiGuardDecision,
    *,
    used_live: bool = False,
) -> MatchIntelligenceReport:
    """Store last guard outcome on the report for UI display."""
    from dataclasses import replace

    meta = dict(report.provider_metadata or {})
    meta["odds_api_guard"] = {
        "allowed": decision.allowed,
        "reason": decision.reason,
        "from_cache": decision.from_cache,
        "used_live": used_live,
        "daily_used": decision.daily_used,
        "monthly_used": decision.monthly_used,
        "daily_soft_limit": decision.daily_soft_limit,
        "daily_hard_limit": decision.daily_hard_limit,
        "monthly_limit": decision.monthly_limit,
    }
    return replace(report, provider_metadata=meta)
