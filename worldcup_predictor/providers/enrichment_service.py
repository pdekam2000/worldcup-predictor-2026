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
        report, outcome = self._maybe_enrich_rapid_football_stats(report, fixture, outcome, endpoint_log)
        report, outcome = self._maybe_enrich_rapid_xg_statistics(report, fixture, outcome, endpoint_log)

        if endpoint_log != (report.api_inspection.endpoints if report.api_inspection else []):
            report = replace(report, api_inspection=ApiInspectionReport(endpoints=endpoint_log))

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

        sport = self._settings.the_odds_api_sport
        endpoint = f"sports/{sport}/odds"
        decision = evaluate_odds_api_call(report, fixture, self._settings, force=force)

        if not decision.allowed:
            outcome.skipped.append(f"odds_api:{decision.reason}")
            return attach_guard_metadata(report, decision), outcome

        if decision.from_cache and decision.cached_event:
            bookmakers = self._odds_bookmakers_from_event(decision.cached_event)
            if bookmakers:
                odds = OddsSnapshot(
                    fixture_id=fixture.id,
                    available=True,
                    bookmakers=bookmakers,
                    source="cache",
                    note="Cached The Odds API data (comparison only — not betting advice).",
                )
                outcome.applied_providers.append("the_odds_api")
                outcome.filled_fields.append("odds")
                missing = [m for m in report.missing_data if m != "odds"]
                report = attach_guard_metadata(report, decision)
                return replace(report, odds=odds, missing_data=missing), outcome
            outcome.skipped.append("odds_api:cache_empty")
            return attach_guard_metadata(report, decision), outcome

        if not self._registry.the_odds_api.is_configured:
            outcome.skipped.append("odds:the_odds_api_not_configured")
            return attach_guard_metadata(report, decision), outcome

        result = self._registry.the_odds_api.get_match_odds(
            home_team=fixture.home_team,
            away_team=fixture.away_team,
        )
        self._log_provider(endpoint_log, result)
        report = attach_guard_metadata(report, decision, used_live=result.available)

        if not result.available:
            if result.error:
                outcome.errors.append(f"the_odds_api: {result.error}")
            else:
                outcome.skipped.append(f"odds_api:{decision.reason}")
            return report, outcome

        bookmakers = self._odds_bookmakers_from_event(result.data)
        if not bookmakers:
            outcome.skipped.append("odds:no_matching_event")
            return report, outcome

        record_odds_api_call(
            fixture_id=fixture.id,
            endpoint=endpoint,
            event=result.data if isinstance(result.data, dict) else None,
        )

        odds = OddsSnapshot(
            fixture_id=fixture.id,
            available=True,
            bookmakers=bookmakers,
            source="live",
            note="Enriched from The Odds API (comparison only — not betting advice).",
        )
        outcome.applied_providers.append("the_odds_api")
        outcome.filled_fields.append("odds")
        missing = [m for m in report.missing_data if m != "odds"]
        return replace(report, odds=odds, missing_data=missing), outcome

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
        )
        self._log_provider(endpoint_log, result)
        if not result.available:
            if result.error and result.configured:
                outcome.errors.append(f"sportmonks: {result.error}")
            else:
                outcome.skipped.append("sportmonks:no_match")
            return report, outcome

        meta = dict(report.provider_metadata or {})
        meta["sportmonks_fixture"] = result.data
        outcome.applied_providers.append("sportmonks")
        outcome.filled_fields.append("sportmonks_context")
        return replace(report, provider_metadata=meta), outcome

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
