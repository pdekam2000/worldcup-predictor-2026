"""The Odds API diagnostics — shared by CLI and GUI (Phase 50B)."""

from __future__ import annotations

import json
from typing import Any

from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.providers.odds_api_credit.config import odds_api_cache_hours
from worldcup_predictor.providers.odds_api_credit.guard import (
    _cache_fresh,
    _needs_external_odds,
    evaluate_odds_api_call,
    usage_summary,
)
from worldcup_predictor.providers.odds_api_credit.repository import get_odds_api_repository
from worldcup_predictor.providers.the_odds_api_provider import TheOddsApiProvider


def run_odds_api_diagnostics(
    fixture_id: int,
    settings: Settings | None = None,
    *,
    force: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Full Odds API diagnostic snapshot for a fixture."""
    settings = settings or get_settings()
    repo = get_odds_api_repository()
    usage = usage_summary(settings)
    cache = repo.get_cache(fixture_id, "h2h,totals")
    cache_status = "miss"
    cache_fresh = False
    if cache:
        cache_status = "hit_fresh" if _cache_fresh(cache["cached_at"]) else "hit_stale"

    report = MatchIntelligenceBuilder(ApiFootballClient(settings)).build_by_fixture_id(
        fixture_id,
        force_odds_api=force and not dry_run,
    )
    fixture = report.fixture
    guard_meta = (report.provider_metadata or {}).get("odds_api_guard") or {}
    consensus_meta = (report.provider_metadata or {}).get("the_odds_api_consensus") or {}
    fetch_meta = (report.provider_metadata or {}).get("the_odds_api_fetch") or {}

    needs, need_reason = _needs_external_odds(report)
    decision = evaluate_odds_api_call(report, fixture, settings, force=force) if fixture else None

    provider = TheOddsApiProvider(settings)
    sport_key = provider.resolve_sport_key(discover=True) if settings.the_odds_api_configured else None
    event_matched = bool(fetch_meta.get("event_matched"))
    event_id = fetch_meta.get("event_id")

    if settings.the_odds_api_configured and fixture and not fetch_meta and dry_run:
        events_result = provider.list_events(sport_key) if sport_key else None
        if events_result and events_result.available and isinstance(events_result.data, list):
            matched = provider.match_event(
                events_result.data,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                kickoff_utc=fixture.kickoff_utc,
            )
            if matched:
                event_matched = True
                event_id = str(matched.get("id", "")) or None

    odds = report.odds
    bookmaker_count = len(odds.bookmakers) if odds and odds.bookmakers else 0
    sharp_score = None
    try:
        from worldcup_predictor.odds.sharp_money_intelligence_engine import build_sharp_money_intelligence

        sharp_score = build_sharp_money_intelligence(report).sharp_money_score
    except Exception:
        pass

    used_live = bool(guard_meta.get("used_live") or fetch_meta.get("odds_api_called"))
    from_cache = bool(guard_meta.get("from_cache") or fetch_meta.get("used_cache"))
    odds_api_called = used_live or (from_cache and guard_meta.get("allowed", True))

    return {
        "fixture_id": fixture_id,
        "key_loaded": settings.the_odds_api_configured,
        "daily_used": usage["daily_used"],
        "monthly_used": usage["monthly_used"],
        "daily_hard_limit": usage.get("daily_hard_limit"),
        "monthly_limit": usage.get("monthly_limit"),
        "cache_status": cache_status,
        "cache_ttl_hours": odds_api_cache_hours(),
        "guard_allowed": decision.allowed if decision else False,
        "guard_reason": guard_meta.get("reason") or (decision.reason if decision else "no_fixture"),
        "needs_external_odds": needs,
        "needs_external_reason": need_reason,
        "sport_key_found": sport_key,
        "event_matched": event_matched,
        "event_id": event_id,
        "odds_api_called": odds_api_called,
        "used_live": used_live,
        "from_cache": from_cache,
        "credits_used": fetch_meta.get("credits_used", 0),
        "bookmaker_count": fetch_meta.get("bookmaker_count") or bookmaker_count,
        "api_football_bookmaker_count": bookmaker_count,
        "sharp_money_score": sharp_score,
        "cross_source_agreement": consensus_meta.get("cross_source_agreement"),
        "consensus": consensus_meta or None,
        "enrichment_sources": list(report.enrichment_sources or []),
        "skip_reason": guard_meta.get("reason") or (decision.reason if decision and not decision.allowed else ""),
    }
