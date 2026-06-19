from __future__ import annotations

from dataclasses import replace
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.clients.api_response import ApiCallResult
from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.data_quality.intelligence_scoring import (
    form_string_from_recent,
)
from worldcup_predictor.domain.fixture import Fixture
from worldcup_predictor.domain.intelligence import (
    ApiInspectionReport,
    DataQualityReport,
    EndpointInspection,
    InjuryReport,
    MatchIntelligenceReport,
    OddsSnapshot,
    TeamIntelligence,
)


class MatchIntelligenceBuilder:
    """Assembles MatchIntelligenceReport from API-Football safe calls."""

    TRACKED_FIELDS = (
        "home_form",
        "away_form",
        "home_statistics",
        "away_statistics",
        "head_to_head",
        "injuries",
        "fixture_statistics",
        "lineups",
        "odds",
    )

    @staticmethod
    def first_or_none(value: Any) -> Any | None:
        if isinstance(value, list) and value:
            return value[0]
        return None

    @staticmethod
    def _extract_api_payload(data: Any) -> Any | None:
        """First list item, or a non-empty dict (teams/statistics returns a single object)."""
        if isinstance(data, list):
            return MatchIntelligenceBuilder.first_or_none(data)
        if isinstance(data, dict) and data:
            return data
        return None

    @staticmethod
    def _non_empty_list(data: Any) -> list[Any]:
        if isinstance(data, list):
            return data
        return []

    def __init__(self, api_client: ApiFootballClient) -> None:
        self._api = api_client

    def build(self, fixture: Fixture, *, force_odds_api: bool = False) -> MatchIntelligenceReport:
        missing_data: list[str] = []
        errors: list[str] = []
        available_fields: list[str] = []
        sources: set[str] = set()
        endpoint_log: list[EndpointInspection] = []

        fixture = self._resolve_fixture(fixture, missing_data, errors, sources, endpoint_log)

        competition = get_competition(fixture.competition_key)
        fixture = self._ensure_fixture_league_season(fixture, competition)
        injuries_league_id, injuries_season = self._resolve_injuries_league_season(fixture, competition)

        injuries_result = self._api.get_injuries(
            fixture_id=fixture.id,
            league_id=injuries_league_id,
            season=injuries_season,
        )
        self._log_endpoint(endpoint_log, "injuries", injuries_result)
        sources.add(injuries_result.source)
        if injuries_result.skip_reason == "missing_league_id":
            missing_data.append("injuries")
        elif injuries_result.error:
            errors.append(f"injuries: {injuries_result.error}")
        injuries_items: list[dict[str, Any]] = self._non_empty_list(
            injuries_result.data if injuries_result.ok else []
        )

        sidelined_meta: dict[str, Any] | None = None
        try:
            from worldcup_predictor.integrations.sidelined_probe import (
                normalize_sidelined,
                sidelined_enabled,
            )

            cache_dir = self._api._settings.api_cache_dir
            if sidelined_enabled(cache_dir):
                existing = {
                    str((i.get("player") or {}).get("name", "")).lower()
                    for i in injuries_items
                    if isinstance(i, dict)
                }
                sidelined_count = 0
                for team_id in (fixture.home_team_id, fixture.away_team_id):
                    if not team_id:
                        continue
                    sidelined_result = self._api.get_sidelined(team_id=int(team_id))
                    self._log_endpoint(endpoint_log, f"sidelined/team/{team_id}", sidelined_result)
                    sources.add(sidelined_result.source)
                    if sidelined_result.ok and isinstance(sidelined_result.data, list):
                        sidelined_rows = normalize_sidelined(sidelined_result.data)
                        sidelined_count += len(sidelined_rows)
                        for row in sidelined_rows:
                            name = str((row.get("player") or {}).get("name", "")).lower()
                            if name and name not in existing:
                                injuries_items.append(row)
                                existing.add(name)
                if sidelined_count:
                    sidelined_meta = {"available": True, "count": sidelined_count}
        except Exception:
            sidelined_meta = None

        home_recent, home_recent_log = self._fetch_recent_fixtures(fixture.home_team_id)
        away_recent, away_recent_log = self._fetch_recent_fixtures(fixture.away_team_id)
        endpoint_log.extend(home_recent_log)
        endpoint_log.extend(away_recent_log)

        home_intel, home_missing, home_errors, home_available = self._build_team_intelligence(
            fixture, side="home", injuries_items=injuries_items, recent_fixtures=home_recent
        )
        away_intel, away_missing, away_errors, away_available = self._build_team_intelligence(
            fixture, side="away", injuries_items=injuries_items, recent_fixtures=away_recent
        )
        missing_data.extend(home_missing)
        missing_data.extend(away_missing)
        errors.extend(home_errors)
        errors.extend(away_errors)
        available_fields.extend(home_available)
        available_fields.extend(away_available)

        if injuries_result.ok and injuries_items:
            available_fields.append("injuries")
        elif injuries_result.ok:
            missing_data.append("injuries")
            errors.append("injuries: empty response")
        else:
            missing_data.append("injuries")

        h2h_result = self._collect_h2h(fixture, missing_data, errors, available_fields, sources, endpoint_log)
        events_result = self._collect_fixture_events(fixture, missing_data, errors, sources, endpoint_log)
        stats_result = self._collect_fixture_stats(fixture, missing_data, errors, available_fields, sources, endpoint_log)
        lineups_result = self._collect_lineups(fixture, missing_data, errors, available_fields, sources, endpoint_log)
        odds_result = self._collect_odds(fixture, missing_data, errors, available_fields, sources, endpoint_log)
        standings_context = self._collect_standings(fixture, competition, missing_data, errors, sources, endpoint_log)

        from worldcup_predictor.intelligence.group_context import extract_group_context

        standings_groups = (
            standings_context.get("groups", []) if standings_context and standings_context.get("available") else []
        )
        group_context = extract_group_context(
            standings_groups,
            home_team_id=fixture.home_team_id,
            away_team_id=fixture.away_team_id,
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            stage=fixture.stage,
        )

        weather_info = self._extract_weather_from_fixture(fixture)
        referee = fixture.referee

        live_sources = sources.intersection({"live", "cache"})
        is_placeholder = not self._api.is_configured or not live_sources
        if self._api.is_configured and live_sources:
            is_placeholder = False

        if "live" in sources:
            primary_source = "live"
        elif "cache" in sources:
            primary_source = "cache"
        else:
            primary_source = "placeholder"

        draft = MatchIntelligenceReport(
            fixture_id=fixture.id,
            fixture=fixture,
            home_team=home_intel,
            away_team=away_intel,
            head_to_head=h2h_result,
            fixture_events=events_result,
            fixture_statistics=stats_result,
            lineups=lineups_result,
            odds=odds_result,
            missing_data=sorted(set(missing_data)),
            source=primary_source,  # type: ignore[arg-type]
            is_placeholder=is_placeholder,
            standings_context=standings_context,
            group_context=group_context,
            home_recent_fixtures=home_recent,
            away_recent_fixtures=away_recent,
            weather=weather_info,
            referee=referee,
            api_inspection=ApiInspectionReport(endpoints=endpoint_log),
        )

        from worldcup_predictor.integrations.api_sports_deep_data import attach_api_sports_deep_data

        draft = attach_api_sports_deep_data(draft, self._api, competition)

        if sidelined_meta:
            supplemental = dict(draft.supplemental_sources or {})
            supplemental["sidelined_audit"] = sidelined_meta
            draft = replace(draft, supplemental_sources=supplemental)

        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.providers.enrichment_service import EnrichmentService

        enrichment = EnrichmentService(get_settings())
        if enrichment.registry.any_enrichment_configured:
            draft, _outcome = enrichment.apply(draft, fixture, force_odds_api=force_odds_api)

        from worldcup_predictor.data_quality.transparency import explain_data_quality

        detail = explain_data_quality(draft)
        data_quality = DataQualityReport(
            score=detail.score_ratio,
            available_fields=sorted(set(available_fields)),
            missing_fields=sorted(set(missing_data)),
            errors=errors,
            breakdown=detail.components,
            breakdown_total=detail.display_total,
            breakdown_max=detail.max_total,
            component_max=detail.component_max,
            pre_match_data_quality=detail.pre_match_total,
            live_data_quality=detail.live_total,
            post_match_data_quality=detail.post_match_total,
            match_phase=detail.match_phase,
            reason_text=detail.reason_text,
            kickoff_note=detail.kickoff_note,
        )
        draft.data_quality = data_quality

        try:
            from worldcup_predictor.odds.snapshot_service import OddsSnapshotService

            OddsSnapshotService().persist_from_report(draft)
        except Exception:
            pass

        return draft

    def build_by_fixture_id(self, fixture_id: int, *, force_odds_api: bool = False) -> MatchIntelligenceReport:
        result = self._api.get_fixture_by_id(fixture_id)
        if result.ok and result.data:
            if result.source == "placeholder":
                placeholder = self._api.resolve_placeholder_fixture(fixture_id)
                if placeholder:
                    return self.build(placeholder, force_odds_api=force_odds_api)
            item = self._extract_api_payload(result.data)
            if item is not None:
                fixture = self._api.parse_fixture_item(item)
                return self.build(fixture, force_odds_api=force_odds_api)

        placeholder = self._api.resolve_placeholder_fixture(fixture_id)
        if placeholder:
            report = self.build(placeholder, force_odds_api=force_odds_api)
            if result.error:
                report.data_quality.errors.append(result.error)  # type: ignore[union-attr]
            return report

        from datetime import datetime

        empty_fixture = Fixture(
            id=fixture_id,
            competition_key="world_cup_2026",
            home_team="Unknown",
            away_team="Unknown",
            kickoff_utc=datetime(2026, 6, 11, 18, 0, 0),
            venue="TBD",
            stage="Unknown",
            league_id=1,
            season=2026,
            source="placeholder",
        )
        report = self.build(empty_fixture)
        report.missing_data.append("fixture")
        if result.error:
            report.data_quality.errors.append(result.error)  # type: ignore[union-attr]
        elif result.ok:
            report.data_quality.errors.append("fixture: empty response")  # type: ignore[union-attr]
        return report

    def _resolve_fixture(
        self,
        fixture: Fixture,
        missing_data: list[str],
        errors: list[str],
        sources: set[str],
        endpoint_log: list[EndpointInspection],
    ) -> Fixture:
        if fixture.home_team_id and fixture.away_team_id:
            sources.add(fixture.source if fixture.source in ("live", "cache", "placeholder") else "placeholder")
            self._log_endpoint(
                endpoint_log,
                "fixtures",
                ApiCallResult(data=[{}], source=fixture.source, endpoint="fixtures"),  # type: ignore[arg-type]
                loaded=True,
            )
            return fixture

        result = self._api.get_fixture_by_id(fixture.id)
        self._log_endpoint(endpoint_log, "fixtures", result)
        sources.add(result.source)
        if result.error:
            errors.append(f"fixture: {result.error}")
        item = self._extract_api_payload(result.data)
        if result.ok and item is not None:
            parsed = self._api.parse_fixture_item(item, competition_key=fixture.competition_key)
            return self._enrich_fixture_metadata(parsed, item)
        if result.ok:
            errors.append("fixture: empty response")
        missing_data.append("fixture_details")
        return fixture

    @staticmethod
    def _enrich_fixture_metadata(fixture: Fixture, item: dict[str, Any]) -> Fixture:
        from dataclasses import replace

        fix = item.get("fixture", {}) or {}
        venue = fix.get("venue", {}) or {}
        referee = (fix.get("referee") or "") or None
        weather_raw = fix.get("weather") or {}
        weather_note = weather_raw if weather_raw else None
        _ = weather_note
        league = item.get("league") or {}
        try:
            league_id = int(league.get("id") or 0)
        except (TypeError, ValueError):
            league_id = 0
        try:
            season = int(league.get("season") or 0)
        except (TypeError, ValueError):
            season = 0
        return replace(
            fixture,
            referee=referee or fixture.referee,
            venue=venue.get("name") or fixture.venue,
            league_id=league_id if league_id > 0 else fixture.league_id,
            season=season if season > 0 else fixture.season,
        )

    @staticmethod
    def _ensure_fixture_league_season(fixture: Fixture, competition) -> Fixture:
        from dataclasses import replace

        league_id = fixture.league_id if fixture.league_id and fixture.league_id > 0 else competition.league_id
        season = fixture.season if fixture.season and fixture.season > 0 else competition.season
        if league_id != fixture.league_id or season != fixture.season:
            return replace(fixture, league_id=league_id, season=season)
        return fixture

    @staticmethod
    def _resolve_injuries_league_season(fixture: Fixture, competition) -> tuple[int | None, int | None]:
        league_id = fixture.league_id if fixture.league_id and fixture.league_id > 0 else None
        season = fixture.season if fixture.season and fixture.season > 0 else None
        if league_id is None and competition.league_id and competition.league_id > 0:
            league_id = int(competition.league_id)
        if season is None and competition.season:
            season = int(competition.season)
        if league_id is None:
            try:
                from worldcup_predictor.database.repository import FootballIntelligenceRepository

                row = FootballIntelligenceRepository().get_fixture_row(fixture.id)
                if row:
                    raw_league = row.get("league_id")
                    if raw_league is not None and int(raw_league) > 0:
                        league_id = int(raw_league)
                    raw_season = row.get("season")
                    if season is None and raw_season is not None and int(raw_season) > 0:
                        season = int(raw_season)
            except Exception:
                pass
        return league_id, season

    def _log_endpoint(
        self,
        log: list[EndpointInspection],
        endpoint: str,
        result: ApiCallResult,
        *,
        loaded: bool | None = None,
    ) -> None:
        api_configured = self._api.is_configured
        if getattr(result, "skip_reason", None):
            status = "skipped"
            is_loaded = False
        elif result.error:
            status = "error"
            is_loaded = False
        elif not api_configured and result.source == "placeholder":
            status = "not_supported"
            is_loaded = False
        elif result.response_count == 0:
            status = "empty"
            is_loaded = False
        elif loaded is False:
            status = "empty"
            is_loaded = False
        else:
            status = "loaded"
            is_loaded = True

        if loaded is True and result.error is None and result.response_count > 0:
            is_loaded = True
            status = "loaded"

        log.append(
            EndpointInspection(
                endpoint=endpoint,
                loaded=is_loaded and result.error is None,
                response_count=result.response_count,
                source=result.source,
                error=result.error,
                status=status,
                skip_reason=getattr(result, "skip_reason", None),
            )
        )

    def _fetch_recent_fixtures(
        self, team_id: int | None
    ) -> tuple[list[dict[str, Any]], list[EndpointInspection]]:
        logs: list[EndpointInspection] = []
        if team_id is None:
            return [], logs
        result = self._api.get_team_recent_fixtures(team_id, last=10)
        self._log_endpoint(logs, f"fixtures/team/{team_id}", result)
        return self._non_empty_list(result.data if result.ok else []), logs

    def _collect_standings(
        self,
        fixture: Fixture,
        competition,
        missing_data: list[str],
        errors: list[str],
        sources: set[str],
        endpoint_log: list[EndpointInspection],
    ) -> dict[str, Any] | None:
        result = self._api.get_standings(competition)
        self._log_endpoint(endpoint_log, "standings", result)
        sources.add(result.source)
        if result.error:
            errors.append(f"standings: {result.error}")
        data = self._non_empty_list(result.data if result.ok else None)
        if not data:
            missing_data.append("standings")
            return {"available": False, "groups": []}
        return {"available": True, "groups": data, "count": len(data)}

    @staticmethod
    def _extract_weather_from_fixture(fixture: Fixture) -> dict[str, Any]:
        return {"available": False, "note": "Weather loaded when present in live fixture payload"}

    def _build_team_intelligence(
        self,
        fixture: Fixture,
        side: str,
        injuries_items: list[dict[str, Any]],
        recent_fixtures: list[dict[str, Any]] | None = None,
    ) -> tuple[TeamIntelligence, list[str], list[str], list[str]]:
        missing: list[str] = []
        errors: list[str] = []
        available: list[str] = []

        team_name = fixture.home_team if side == "home" else fixture.away_team
        team_id = fixture.home_team_id if side == "home" else fixture.away_team_id
        prefix = "home" if side == "home" else "away"

        form: list[str] | None = None
        statistics: dict[str, Any] | None = None
        source = "placeholder"

        if team_id is None:
            missing.append(f"{prefix}_team_id")
        else:
            stats_result = self._api.get_team_statistics(
                team_id=team_id,
                league_id=fixture.league_id,
                season=fixture.season,
            )
            source = stats_result.source
            if stats_result.error:
                errors.append(f"{prefix}_statistics: {stats_result.error}")
            raw = self._extract_api_payload(stats_result.data)
            if stats_result.ok and raw:
                form_str = raw.get("form") or ""
                form = list(form_str) if form_str else None
                statistics = raw
                if form:
                    available.append(f"{prefix}_form")
                available.append(f"{prefix}_statistics")
            elif stats_result.ok:
                missing.append(f"{prefix}_statistics")
                errors.append(f"{prefix}_statistics: empty response")
            else:
                missing.append(f"{prefix}_statistics")

        if form is None and team_id is not None and recent_fixtures:
            derived = form_string_from_recent(recent_fixtures, team_id)
            if derived:
                form = derived
                available.append(f"{prefix}_form")

        if statistics is None and recent_fixtures:
            statistics = {"recent_fixtures_count": len(recent_fixtures), "source": "recent_fixtures"}
            available.append(f"{prefix}_recent_form")

        injury_players = [
            item
            for item in injuries_items
            if (team_id and item.get("team", {}).get("id") == team_id)
            or item.get("team", {}).get("name") == team_name
        ]
        injuries = InjuryReport(
            team_name=team_name,
            team_id=team_id,
            players=injury_players,
            source=source,  # type: ignore[arg-type]
            available=True,
        )

        return (
            TeamIntelligence(
                team_name=team_name,
                team_id=team_id,
                form=form,
                statistics=statistics,
                injuries=injuries,
                source=source,  # type: ignore[arg-type]
            ),
            missing,
            errors,
            available,
        )

    def _collect_h2h(
        self,
        fixture: Fixture,
        missing_data: list[str],
        errors: list[str],
        available_fields: list[str],
        sources: set[str],
        endpoint_log: list[EndpointInspection],
    ) -> dict[str, Any] | None:
        if not fixture.home_team_id or not fixture.away_team_id:
            missing_data.append("head_to_head")
            return None

        result = self._api.get_head_to_head(fixture.home_team_id, fixture.away_team_id)
        self._log_endpoint(endpoint_log, "fixtures/headtohead", result)
        sources.add(result.source)
        data = self._process_result(result, "head_to_head", missing_data, errors, available_fields)
        if data:
            return {"meetings": data, "count": len(data)}
        return None

    def _collect_fixture_events(
        self,
        fixture: Fixture,
        missing_data: list[str],
        errors: list[str],
        sources: set[str],
        endpoint_log: list[EndpointInspection],
    ) -> list[dict[str, Any]] | None:
        result = self._api.get_fixture_events(fixture.id)
        self._log_endpoint(endpoint_log, "fixtures/events", result)
        sources.add(result.source)
        if result.error:
            errors.append(f"fixture_events: {result.error}")
        events = self._non_empty_list(result.data if result.ok else None)
        if events:
            return events
        missing_data.append("fixture_events")
        if result.ok:
            errors.append("fixture_events: empty response")
        return []

    def _collect_fixture_stats(
        self,
        fixture: Fixture,
        missing_data: list[str],
        errors: list[str],
        available_fields: list[str],
        sources: set[str],
        endpoint_log: list[EndpointInspection],
    ) -> dict[str, Any] | None:
        result = self._api.get_fixture_statistics(fixture.id)
        self._log_endpoint(endpoint_log, "fixtures/statistics", result)
        sources.add(result.source)
        processed = self._process_result(result, "fixture_statistics", missing_data, errors, available_fields)
        if processed:
            return {"items": processed}
        return None

    def _collect_lineups(
        self,
        fixture: Fixture,
        missing_data: list[str],
        errors: list[str],
        available_fields: list[str],
        sources: set[str],
        endpoint_log: list[EndpointInspection],
    ) -> dict[str, Any] | None:
        from worldcup_predictor.quota.cache_policy import should_fetch_lineups

        if not should_fetch_lineups(fixture.kickoff_utc):
            missing_data.append("lineups")
            return {"items": [], "available": False, "skipped": "far_from_kickoff"}
        result = self._api.get_fixture_lineups(fixture.id)
        self._log_endpoint(endpoint_log, "fixtures/lineups", result)
        sources.add(result.source)
        processed = self._process_result(result, "lineups", missing_data, errors, available_fields)
        if processed:
            return {"items": processed, "available": bool(processed)}
        missing_data.append("lineups")
        return {"items": [], "available": False}

    def _collect_odds(
        self,
        fixture: Fixture,
        missing_data: list[str],
        errors: list[str],
        available_fields: list[str],
        sources: set[str],
        endpoint_log: list[EndpointInspection],
    ) -> OddsSnapshot | None:
        result = self._api.get_odds(fixture.id)
        self._log_endpoint(endpoint_log, "odds", result)
        sources.add(result.source)
        if result.error:
            errors.append(f"odds: {result.error}")

        bookmakers: list[dict[str, Any]] = []
        odds_items = self._non_empty_list(result.data if result.ok else None)
        if odds_items:
            for item in odds_items:
                if isinstance(item, dict):
                    bookmakers.extend(item.get("bookmakers", []))
            if bookmakers:
                available_fields.append("odds")
                return OddsSnapshot(
                    fixture_id=fixture.id,
                    bookmakers=bookmakers,
                    source=result.source,
                    available=True,
                )
            missing_data.append("odds")
            errors.append("odds: empty response")
        else:
            missing_data.append("odds")
            if result.ok:
                errors.append("odds: empty response")
        return OddsSnapshot(
            fixture_id=fixture.id,
            source=result.source,
            available=False,
            error=result.error,
        )

    @staticmethod
    def _process_result(
        result: ApiCallResult,
        field_name: str,
        missing_data: list[str],
        errors: list[str],
        available_fields: list[str],
    ) -> Any | None:
        if result.error:
            errors.append(f"{field_name}: {result.error}")
        payload = MatchIntelligenceBuilder._extract_api_payload(result.data)
        if isinstance(result.data, list) and result.ok and not result.data:
            missing_data.append(field_name)
            errors.append(f"{field_name}: empty response")
            return None
        if result.ok and payload is not None:
            if isinstance(result.data, list):
                if not result.data:
                    missing_data.append(field_name)
                    errors.append(f"{field_name}: empty response")
                    return None
                available_fields.append(field_name)
                return result.data
            available_fields.append(field_name)
            return result.data
        missing_data.append(field_name)
        return None
