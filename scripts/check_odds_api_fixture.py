"""Diagnose The Odds API integration for a single fixture."""

from __future__ import annotations

import json
import sys

from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.providers.odds_api_credit.config import (
    odds_api_cache_hours,
    odds_api_low_bookmaker_count,
    odds_api_low_sharp_score,
)
from worldcup_predictor.providers.odds_api_credit.guard import (
    _cache_fresh,
    _needs_external_odds,
    evaluate_odds_api_call,
    usage_summary,
)
from worldcup_predictor.providers.odds_api_credit.repository import get_odds_api_repository


def main() -> int:
    fixture_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1489374
    settings = get_settings()
    key_loaded = settings.the_odds_api_configured

    repo = get_odds_api_repository()
    usage = usage_summary(settings)
    cache = repo.get_cache(fixture_id, "h2h,totals")
    cache_status = "miss"
    cache_fresh = False
    if cache:
        cache_status = "hit"
        cache_fresh = _cache_fresh(cache["cached_at"])

    conn = repo._connection()
    fixture_rows = conn.execute(
        """
        SELECT usage_date, endpoint, credits_used, created_at
        FROM odds_api_usage WHERE fixture_id = ? ORDER BY created_at DESC LIMIT 10
        """,
        (fixture_id,),
    ).fetchall()

    report = MatchIntelligenceBuilder(ApiFootballClient(settings)).build_by_fixture_id(
        fixture_id, force_odds_api=False
    )
    fixture = report.fixture
    guard_meta = (report.provider_metadata or {}).get("odds_api_guard") or {}
    enrichment = list(report.enrichment_sources or [])
    odds = report.odds
    bookmaker_count = len(odds.bookmakers) if odds and odds.bookmakers else 0

    needs, need_reason = _needs_external_odds(report)
    sharp_score = None
    try:
        from worldcup_predictor.odds.sharp_money_intelligence_engine import build_sharp_money_intelligence

        sharp_score = build_sharp_money_intelligence(report).sharp_money_score
    except Exception as exc:
        sharp_score = str(exc)

    decision = evaluate_odds_api_call(report, fixture, settings, force=False)

    used_live = bool(guard_meta.get("used_live"))
    from_cache = bool(guard_meta.get("from_cache"))
    odds_api_used = used_live or (from_cache and guard_meta.get("allowed"))
    if not guard_meta:
        odds_api_used = "the_odds_api" in enrichment

    skip_reason = guard_meta.get("reason") or decision.reason
    if not key_loaded:
        skip_reason = "not_configured"
    elif odds_api_used and from_cache:
        skip_reason = "cache_hit"
    elif odds_api_used and used_live:
        skip_reason = "live_call"

    out = {
        "fixture_id": fixture_id,
        "the_odds_api_key_loaded": key_loaded,
        "the_odds_api_key_length": len(settings.the_odds_api_key.strip()) if key_loaded else 0,
        "odds_api_used": odds_api_used,
        "used_live": used_live,
        "from_cache": from_cache,
        "skip_reason": skip_reason if not odds_api_used else ("cache_hit" if from_cache else "live_call"),
        "cache_status": f"{cache_status}{'_fresh' if cache_fresh else '_stale' if cache else ''}",
        "monthly_usage": usage["monthly_used"],
        "daily_usage": usage["daily_used"],
        "monthly_limit": usage.get("monthly_limit"),
        "daily_hard_limit": usage.get("daily_hard_limit"),
        "api_football_bookmaker_count": bookmaker_count,
        "low_bookmaker_threshold": odds_api_low_bookmaker_count(),
        "sharp_money_score": sharp_score,
        "low_sharp_threshold": odds_api_low_sharp_score(),
        "needs_external_odds": needs,
        "needs_external_reason": need_reason,
        "guard_decision": {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "from_cache": decision.from_cache,
        },
        "provider_metadata_guard": guard_meta,
        "enrichment_sources": enrichment,
        "odds_source": odds.source if odds else None,
        "odds_note": odds.note if odds else None,
        "fixture_usage_rows": [dict(r) for r in fixture_rows],
        "cache_cached_at": cache["cached_at"] if cache else None,
        "cache_ttl_hours": odds_api_cache_hours(),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
