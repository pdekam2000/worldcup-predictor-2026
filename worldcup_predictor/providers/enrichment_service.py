"""Merge optional provider data into intelligence reports — API-Sports remains primary."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from worldcup_predictor.config.settings import Settings
from worldcup_predictor.domain.fixture import Fixture
from worldcup_predictor.domain.intelligence import (
    ApiInspectionReport,
    EndpointInspection,
    MatchIntelligenceReport,
    OddsSnapshot,
)
from worldcup_predictor.providers.base import EnrichmentOutcome, ProviderCallResult
from worldcup_predictor.providers.registry import ProviderRegistry


class EnrichmentService:
    """
    Apply optional enrichment providers after primary API-Sports collection.

    Rules:
      - Never overwrite populated API-Sports fields
      - Only fill gaps (empty odds, missing weather, etc.)
      - Skip providers that are not configured
      - No mock / placeholder fallback
    """

    def __init__(self, settings: Settings, registry: ProviderRegistry | None = None) -> None:
        self._settings = settings
        self._registry = registry or ProviderRegistry(settings)

    @property
    def registry(self) -> ProviderRegistry:
        return self._registry

    def apply(
        self,
        report: MatchIntelligenceReport,
        fixture: Fixture,
        *,
        force_odds_api: bool = False,
    ) -> tuple[MatchIntelligenceReport, EnrichmentOutcome]:
        if not self._registry.any_enrichment_configured:
            return report, EnrichmentOutcome(skipped=["no_enrichment_providers_configured"])

        outcome = EnrichmentOutcome()
        endpoint_log = list(report.api_inspection.endpoints if report.api_inspection else [])

        report, outcome = self._maybe_enrich_odds(report, fixture, outcome, endpoint_log, force=force_odds_api)
        report, outcome = self._maybe_enrich_weather(report, fixture, outcome, endpoint_log)
        report, outcome = self._maybe_enrich_sportmonks(report, fixture, outcome, endpoint_log)
        report, outcome = self._maybe_enrich_sportmonks_standings(report, fixture, outcome, endpoint_log)
        report, outcome = self._maybe_enrich_rapid_football_stats(report, fixture, outcome, endpoint_log)
        report, outcome = self._maybe_enrich_rapid_xg_statistics(report, fixture, outcome, endpoint_log)

        if endpoint_log != (report.api_inspection.endpoints if report.api_inspection else []):
            report = replace(report, api_inspection=ApiInspectionReport(endpoints=endpoint_log))

        from worldcup_predictor.providers.sportmonks_consumption import apply_sportmonks_consumption

        report = apply_sportmonks_consumption(report)

        sources = list(report.enrichment_sources or [])
        for name in outcome.applied_providers:
            if name not in sources:
                sources.append(name)
        report = replace(report, enrichment_sources=sources)
        return report, outcome

    def _maybe_enrich_rapid_football_stats(
        self,
        report: MatchIntelligenceReport,
        fixture: Fixture,
        outcome: EnrichmentOutcome,
        endpoint_log: list[EndpointInspection],
    ) -> tuple[MatchIntelligenceReport, EnrichmentOutcome]:
        client = self._registry.rapid_football_stats
        if not client.is_configured:
            return report, outcome

        kickoff_date = fixture.kickoff_utc.strftime("%Y-%m-%d") if fixture.kickoff_utc else None
        bundle = client.fetch_match_enrichment(
            fixture_id=fixture.id,
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            kickoff_date=kickoff_date,
        )

        for call in bundle.calls:
            if call.error:
                status = "error"
            elif call.loaded:
                status = "loaded"
            else:
                status = "empty"
            endpoint_log.append(
                EndpointInspection(
                    endpoint=call.endpoint,
                    loaded=call.loaded,
                    response_count=call.response_count,
                    source="live" if call.error is None else "error",
                    error=call.error,
                    status=status,
                )
            )

        supplemental = dict(report.supplemental_sources or {})
        if bundle.endpoints_loaded == 0:
            outcome.skipped.append("rapid_football_stats:no_data")
            return report, outcome

        supplemental["rapid_football_stats"] = bundle.to_supplemental_dict()
        outcome.applied_providers.append("rapid_football_stats")
        filled: list[str] = []
        if bundle.xg or bundle.npxg:
            filled.append("supplemental_xg")
        if bundle.player_statistics:
            filled.append("supplemental_player_stats")
        if bundle.prematch_odds or bundle.live_odds or bundle.historical_odds:
            filled.append("supplemental_odds")
        if bundle.match_statistics:
            filled.append("supplemental_match_stats")
        if bundle.match_events:
            filled.append("supplemental_events")
        outcome.filled_fields.extend(filled)

        updated = replace(report, supplemental_sources=supplemental)

        if (not updated.odds or not updated.odds.available) and (
            bundle.prematch_odds or bundle.live_odds
        ):
            odds_payload = bundle.prematch_odds or bundle.live_odds or {}
            bookmakers = odds_payload if isinstance(odds_payload, list) else [odds_payload]
            updated = replace(
                updated,
                odds=OddsSnapshot(
                    fixture_id=fixture.id,
                    available=True,
                    bookmakers=[b for b in bookmakers if isinstance(b, dict)],
                    source="live",
                    note="Supplemental odds from RapidAPI (comparison only — not betting advice).",
                ),
                missing_data=[m for m in updated.missing_data if m != "odds"],
            )

        if not updated.fixture_statistics and bundle.match_statistics:
            updated = replace(
                updated,
                fixture_statistics={"items": [bundle.match_statistics], "source": "rapid_football_stats"},
            )

        if not updated.fixture_events and bundle.match_events:
            updated = replace(updated, fixture_events=bundle.match_events)

        return updated, outcome

    def _maybe_enrich_rapid_xg_statistics(
        self,
        report: MatchIntelligenceReport,
        fixture: Fixture,
        outcome: EnrichmentOutcome,
        endpoint_log: list[EndpointInspection],
    ) -> tuple[MatchIntelligenceReport, EnrichmentOutcome]:
        client = self._registry.rapid_xg_statistics
        if not client.is_configured:
            return report, outcome

        kickoff_date = fixture.kickoff_utc.strftime("%Y-%m-%d") if fixture.kickoff_utc else None
        bundle = client.fetch_match_enrichment(
            fixture_id=fixture.id,
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            kickoff_date=kickoff_date,
        )

        for call in bundle.calls:
            if call.error:
                status = "error"
            elif call.loaded:
                status = "loaded"
            else:
                status = "empty"
            endpoint_log.append(
                EndpointInspection(
                    endpoint=call.endpoint,
                    loaded=call.loaded,
                    response_count=call.response_count,
                    source="live" if call.error is None else "error",
                    error=call.error,
                    status=status,
                )
            )

        supplemental = dict(report.supplemental_sources or {})
        if bundle.endpoints_loaded == 0:
            outcome.skipped.append("rapid_xg_statistics:no_data")
            return report, outcome

        supplemental["rapid_xg_statistics"] = bundle.to_supplemental_dict()
        outcome.applied_providers.append("rapid_xg_statistics")
        if bundle.xg or bundle.npxg:
            outcome.filled_fields.append("supplemental_xg")
        if bundle.upcoming_odds:
            outcome.filled_fields.append("supplemental_odds")

        updated = replace(report, supplemental_sources=supplemental)
        if (not updated.odds or not updated.odds.available) and bundle.upcoming_odds:
            updated = replace(
                updated,
                odds=OddsSnapshot(
                    fixture_id=fixture.id,
                    available=True,
                    bookmakers=[row for row in bundle.upcoming_odds if isinstance(row, dict)],
                    source="live",
                    note="Supplemental odds from Rapid XG Statistics (comparison only — not betting advice).",
                ),
                missing_data=[m for m in updated.missing_data if m != "odds"],
            )
        return updated, outcome

    def _maybe_enrich_odds(
        self,
        report: MatchIntelligenceReport,
        fixture: Fixture,
        outcome: EnrichmentOutcome,
        endpoint_log: list[EndpointInspection],
        *,
        force: bool = False,
    ) -> tuple[MatchIntelligenceReport, EnrichmentOutcome]:
        from worldcup_predictor.providers.odds_api_credit import (
            attach_guard_metadata,
            evaluate_odds_api_call,
            record_odds_api_call,
        )
        from worldcup_predictor.providers.the_odds_api_provider import (
            TheOddsApiProvider,
            build_market_consensus,
        )

        provider = TheOddsApiProvider(self._settings)
        sport = self._settings.the_odds_api_sport
        endpoint = f"sports/{sport}/events/{{eventId}}/odds"
        decision = evaluate_odds_api_call(report, fixture, self._settings, force=force)

        if not decision.allowed:
            outcome.skipped.append(f"odds_api:{decision.reason}")
            return attach_guard_metadata(report, decision), outcome

        fetch = provider.fetch_for_fixture(
            fixture,
            cached_event=decision.cached_event if decision.from_cache else None,
            allow_live=not decision.from_cache,
            fallback_sport_odds=force,
        )

        meta = dict(report.provider_metadata or {})
        meta["the_odds_api_fetch"] = fetch.to_dict()
        meta["odds_api_guard"] = {
            "allowed": decision.allowed,
            "reason": decision.reason if not fetch.odds_api_called else ("cache_hit" if fetch.used_cache else fetch.error or decision.reason),
            "from_cache": fetch.used_cache or decision.from_cache,
            "used_live": fetch.odds_api_called and not fetch.used_cache,
            "daily_used": decision.daily_used,
            "monthly_used": decision.monthly_used,
            "daily_soft_limit": decision.daily_soft_limit,
            "daily_hard_limit": decision.daily_hard_limit,
            "monthly_limit": decision.monthly_limit,
            "credits_used": fetch.credits_used,
            "sport_key": fetch.sport_key,
            "event_id": fetch.event_id,
            "event_matched": fetch.event_matched,
        }
        report = attach_guard_metadata(report, decision, used_live=bool(fetch.odds_api_called and not fetch.used_cache))

        if fetch.error and not fetch.event:
            outcome.skipped.append(f"odds_api:{fetch.error}")
            return replace(report, provider_metadata=meta), outcome

        if not fetch.event:
            outcome.skipped.append(f"odds_api:{fetch.error or 'no_event'}")
            return replace(report, provider_metadata=meta), outcome

        consensus = fetch.consensus or build_market_consensus(
            fetch.event,
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            primary_odds=report.odds,
        )
        meta["the_odds_api_consensus"] = consensus.to_dict()

        if fetch.odds_api_called and not fetch.used_cache:
            record_odds_api_call(
                fixture_id=fixture.id,
                endpoint=fetch.endpoint or endpoint,
                event=fetch.event,
                credits=fetch.credits_used or provider.credits_per_odds_call,
                source="live",
                settings=self._settings,
            )
            from worldcup_predictor.providers.base import ProviderCallResult, ProviderTier

            self._log_provider(
                endpoint_log,
                ProviderCallResult(
                    data=fetch.event,
                    provider="the_odds_api",
                    tier=ProviderTier.ENRICHMENT,
                    endpoint=fetch.endpoint or endpoint,
                ),
            )
            outcome.applied_providers.append("the_odds_api")
            outcome.filled_fields.append("the_odds_api_consensus")
        elif fetch.used_cache:
            outcome.applied_providers.append("the_odds_api")
            outcome.filled_fields.append("the_odds_api_consensus_cache")

        supplemental = dict(report.supplemental_sources or {})
        supplemental["the_odds_api"] = {
            "event_id": fetch.event_id,
            "sport_key": fetch.sport_key,
            "bookmakers": fetch.event.get("bookmakers") or [],
            "consensus": consensus.to_dict(),
            "source": "cache" if fetch.used_cache else "live",
        }

        updated = replace(report, provider_metadata=meta, supplemental_sources=supplemental)
        if not updated.odds or not updated.odds.available:
            bookmakers = fetch.event.get("bookmakers") or []
            updated = replace(
                updated,
                odds=OddsSnapshot(
                    fixture_id=fixture.id,
                    available=bool(bookmakers),
                    bookmakers=[b for b in bookmakers if isinstance(b, dict)],
                    source="live" if fetch.odds_api_called else "cache",
                    note="The Odds API supplemental odds — comparison only, not betting advice.",
                ),
                missing_data=[m for m in updated.missing_data if m != "odds"],
            )
        return updated, outcome

    def _maybe_enrich_weather(
        self,
        report: MatchIntelligenceReport,
        fixture: Fixture,
        outcome: EnrichmentOutcome,
        endpoint_log: list[EndpointInspection],
    ) -> tuple[MatchIntelligenceReport, EnrichmentOutcome]:
        if report.weather and report.weather.get("available"):
            outcome.skipped.append("weather:primary_present")
            return report, outcome

        city = fixture.venue.split(",")[-1].strip() if fixture.venue and "," in fixture.venue else (fixture.venue or "TBD")
        if city == "TBD":
            outcome.skipped.append("weather:no_venue_city")
            return report, outcome

        kickoff_utc = fixture.kickoff_utc

        if self._registry.weather.is_configured:
            result = self._registry.weather.get_venue_forecast(city=city)
            self._log_provider(endpoint_log, result)
            if result.available:
                outcome.applied_providers.append(result.provider)
                outcome.filled_fields.append("weather")
                return replace(report, weather=result.data), outcome
            if result.error:
                outcome.errors.append(f"weather:{result.provider}: {result.error}")

        rapid = self._registry.rapid_open_weather
        if rapid.is_configured:
            rapid_result = rapid.get_venue_weather(city=city, kickoff_utc=kickoff_utc)
            endpoint_log.append(
                EndpointInspection(
                    endpoint=rapid_result.endpoint,
                    loaded=rapid_result.loaded,
                    response_count=rapid_result.response_count,
                    source="live" if rapid_result.error is None else "error",
                    error=rapid_result.error,
                    status="loaded" if rapid_result.loaded else "error",
                )
            )
            if rapid_result.loaded and rapid_result.data:
                outcome.applied_providers.append("rapid_open_weather")
                outcome.filled_fields.append("weather")
                supplemental = dict(report.supplemental_sources or {})
                supplemental["rapid_open_weather"] = {
                    "provider": "rapid_open_weather",
                    "endpoints_loaded": 1 if rapid_result.loaded else 0,
                    "weather": rapid_result.data,
                }
                return replace(
                    report,
                    weather=rapid_result.data,
                    supplemental_sources=supplemental,
                    missing_data=[m for m in report.missing_data if m != "weather"],
                ), outcome
            if rapid_result.error:
                outcome.errors.append(f"rapid_open_weather: {rapid_result.error}")

        outcome.skipped.append("weather:unavailable")
        return report, outcome

    def _maybe_enrich_sportmonks(
        self,
        report: MatchIntelligenceReport,
        fixture: Fixture,
        outcome: EnrichmentOutcome,
        endpoint_log: list[EndpointInspection],
    ) -> tuple[MatchIntelligenceReport, EnrichmentOutcome]:
        if not self._registry.sportmonks.is_configured:
            outcome.skipped.append("sportmonks:not_configured")
            return report, outcome

        kickoff_date = fixture.kickoff_utc.strftime("%Y-%m-%d") if fixture.kickoff_utc else None
        result = self._registry.sportmonks.get_fixture_context(
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            kickoff_date=kickoff_date,
            api_fixture_id=fixture.id,
            competition_key=fixture.competition_key,
        )
        self._log_provider(endpoint_log, result)
        trace = result.trace or {}
        lookup_endpoint = trace.get("lookup_endpoint")
        if lookup_endpoint and lookup_endpoint != result.endpoint:
            endpoint_log.append(
                EndpointInspection(
                    endpoint=f"sportmonks/{lookup_endpoint}",
                    loaded=True,
                    response_count=1,
                    source="cache" if trace.get("api_calls_made", 1) == 0 else "live",
                    error=None,
                    status="loaded",
                )
            )
        if not result.available:
            if result.error and result.configured:
                outcome.errors.append(f"sportmonks: {result.error}")
            else:
                outcome.skipped.append("sportmonks:no_match")
            return report, outcome

        meta = dict(report.provider_metadata or {})
        meta["sportmonks_fixture"] = result.data
        if trace:
            meta["sportmonks_unified"] = trace
        outcome.applied_providers.append("sportmonks")
        outcome.filled_fields.append("sportmonks_context")
        if trace.get("enrichment_endpoint"):
            outcome.filled_fields.append("sportmonks_unified_enrichment")
        return replace(report, provider_metadata=meta), outcome

    def _maybe_enrich_sportmonks_standings(
        self,
        report: MatchIntelligenceReport,
        fixture: Fixture,
        outcome: EnrichmentOutcome,
        endpoint_log: list[EndpointInspection],
    ) -> tuple[MatchIntelligenceReport, EnrichmentOutcome]:
        if not self._registry.sportmonks.is_configured:
            outcome.skipped.append("sportmonks_standings:not_configured")
            return report, outcome
        if fixture.competition_key != "world_cup_2026":
            outcome.skipped.append("sportmonks_standings:competition_skipped")
            return report, outcome

        from worldcup_predictor.intelligence.sportmonks_standings_service import (
            fetch_worldcup_standings,
        )
        from worldcup_predictor.intelligence.tournament_context_engine import (
            SPORTMONKS_TOURNAMENT_STANDINGS_KEY,
        )

        block = fetch_worldcup_standings(settings=self._settings)
        endpoint_log.append(
            EndpointInspection(
                endpoint=f"sportmonks/{block.get('endpoint', '/standings/seasons')}",
                loaded=bool(block.get("available")),
                response_count=int(block.get("team_count") or 0),
                source="cache" if block.get("from_cache") else "live",
                error=block.get("message") if not block.get("available") else None,
                status="loaded" if block.get("available") else "empty",
            )
        )
        if not block.get("available"):
            outcome.skipped.append("sportmonks_standings:unavailable")
            return report, outcome

        supplemental = dict(report.supplemental_sources or {})
        supplemental[SPORTMONKS_TOURNAMENT_STANDINGS_KEY] = block
        outcome.applied_providers.append("sportmonks_standings")
        outcome.filled_fields.append("sportmonks_tournament_standings")
        return replace(report, supplemental_sources=supplemental), outcome

    @staticmethod
    def _odds_bookmakers_from_event(event: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not event:
            return []
        bookmakers = event.get("bookmakers") or []
        return [b for b in bookmakers if isinstance(b, dict)]

    @staticmethod
    def _log_provider(endpoint_log: list[EndpointInspection], result: ProviderCallResult) -> None:
        if result.error:
            status = "error"
        elif not result.configured:
            status = "not_supported"
        elif result.available:
            status = "loaded"
        else:
            status = "empty"
        endpoint_log.append(
            EndpointInspection(
                endpoint=f"{result.provider}/{result.endpoint}",
                loaded=result.available,
                response_count=1 if result.available else 0,
                source="live" if result.available else "placeholder",
                error=result.error,
                status=status,
            )
        )
