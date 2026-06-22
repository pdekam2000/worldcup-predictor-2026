"""EGIE Phase 1B — API-Football Premier League raw ingest into PostgreSQL."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import CompetitionConfig, get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.config import (
    PREMIER_LEAGUE_API_FOOTBALL_JOB,
    PROVIDER_API_FOOTBALL,
    get_ingest_job,
)
from worldcup_predictor.egie.guards import ingest_mode
from worldcup_predictor.clients.api_response import ApiCallResult
from worldcup_predictor.egie.models import EgieIngestRunResult
from worldcup_predictor.egie.storage.repository import EgieRawStoreRepository

logger = logging.getLogger(__name__)

_FINISHED_STATUSES = frozenset({"FT", "AET", "PEN", "AWD", "WO"})


class ApiFootballPremierLeagueIngestor:
    """Fetch API-Football resources and persist raw JSON to PostgreSQL."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = ApiFootballClient(self.settings)
        self.store = EgieRawStoreRepository(self.settings)
        self.job = PREMIER_LEAGUE_API_FOOTBALL_JOB

    def run(
        self,
        *,
        season: int | None = None,
        max_fixtures: int | None = None,
        include_fixture_details: bool = True,
        job_key: str = PREMIER_LEAGUE_API_FOOTBALL_JOB.job_key,
    ) -> EgieIngestRunResult:
        spec = get_ingest_job(job_key)
        comp = get_competition(spec.competition_key)
        if comp is None:
            raise ValueError(f"Competition not found: {spec.competition_key}")
        use_season = int(season if season is not None else spec.season)

        started = datetime.now(timezone.utc)
        result = EgieIngestRunResult(
            job_key=spec.job_key,
            provider=spec.provider,
            competition_key=spec.competition_key,
            season=use_season,
            status="running",
            started_at=started,
        )

        if not self.settings.api_football_configured:
            result.status = "failed"
            result.errors.append("API_FOOTBALL_KEY not configured")
            result.finished_at = datetime.now(timezone.utc)
            return result

        run_config = {
            "season": use_season,
            "max_fixtures": max_fixtures,
            "include_fixture_details": include_fixture_details,
            "resource_types": list(spec.resource_types),
        }
        result.run_id = self.store.start_ingest_run(
            job_key=spec.job_key,
            provider=spec.provider,
            competition_key=spec.competition_key,
            season=use_season,
            config=run_config,
        )

        with ingest_mode():
            try:
                self._ingest_standings(comp, use_season, result)
                fixtures = self._ingest_fixtures(comp, use_season, result)
                if max_fixtures is not None and max_fixtures > 0:
                    fixtures = fixtures[: int(max_fixtures)]

                if include_fixture_details:
                    for item in fixtures:
                        self._ingest_fixture_details(item, comp, use_season, result)
                        result.fixtures_processed += 1

                result.status = "completed" if not result.errors else "completed_with_errors"
            except Exception as exc:
                logger.exception("EGIE Premier League ingest failed")
                result.errors.append(str(exc))
                result.status = "failed"

        result.finished_at = datetime.now(timezone.utc)
        if result.run_id:
            self.store.finish_ingest_run(
                result.run_id,
                status=result.status,
                stats={
                    "api_calls_live": result.api_calls_live,
                    "rows_saved": result.rows_saved,
                    "rows_skipped_duplicate": result.rows_skipped_duplicate,
                    "fixtures_processed": result.fixtures_processed,
                    "resource_counts": result.resource_counts,
                },
                errors=result.errors,
            )
        return result

    def _track_api(self, api_result: Any, result: EgieIngestRunResult) -> Any:
        if getattr(api_result, "source", None) == "live":
            result.api_calls_live += 1
        return api_result

    def _save_api_payload(
        self,
        *,
        resource_type: str,
        request_endpoint: str,
        request_params: dict[str, Any],
        api_result: Any,
        result: EgieIngestRunResult,
        competition_key: str,
        league_id: int,
        season: int,
        fixture_id: int | None = None,
        team_id: int | None = None,
    ) -> None:
        if api_result.data is None:
            return
        envelope = {
            "endpoint": request_endpoint,
            "params": request_params,
            "response": api_result.data,
            "source": api_result.source,
            "error": api_result.error,
        }
        save = self.store.save_raw_response(
            provider=PROVIDER_API_FOOTBALL,
            resource_type=resource_type,
            request_endpoint=request_endpoint,
            request_params=request_params,
            payload_json=envelope,
            source=str(api_result.source),
            competition_key=competition_key,
            league_id=league_id,
            season=season,
            fixture_id=fixture_id,
            team_id=team_id,
            http_status=200 if api_result.ok else None,
        )
        result.resource_counts[resource_type] = result.resource_counts.get(resource_type, 0) + 1
        if save.saved:
            result.rows_saved += 1
        elif save.skipped_duplicate:
            result.rows_skipped_duplicate += 1

    def _ingest_standings(
        self,
        comp: CompetitionConfig,
        season: int,
        result: EgieIngestRunResult,
    ) -> None:
        params = comp.standings_query_params()
        params["season"] = season
        api = self._track_api(self.client.get_standings(comp), result)
        self._save_api_payload(
            resource_type="standings",
            request_endpoint="standings",
            request_params=params,
            api_result=api,
            result=result,
            competition_key=comp.key,
            league_id=comp.league_id,
            season=season,
        )

    def _ingest_fixtures(
        self,
        comp: CompetitionConfig,
        season: int,
        result: EgieIngestRunResult,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"league": comp.league_id, "season": season}
        api = self._track_api(
            self.client.get_historical_fixtures(league_id=comp.league_id, season=season),
            result,
        )
        items = api.data if isinstance(api.data, list) else []
        self._save_api_payload(
            resource_type="fixtures",
            request_endpoint="fixtures",
            request_params=params,
            api_result=api,
            result=result,
            competition_key=comp.key,
            league_id=comp.league_id,
            season=season,
        )

        # Also persist each fixture as addressable raw row for point lookups
        for item in items:
            if not isinstance(item, dict):
                continue
            fid = self._extract_fixture_id(item)
            if fid is None:
                continue
            single_params = {"id": fid}
            single_api = ApiCallResult(
                data=[item],
                source=api.source,
                endpoint="fixtures",
                error=api.error,
            )
            self._save_api_payload(
                resource_type="fixtures",
                request_endpoint="fixtures",
                request_params=single_params,
                api_result=single_api,
                result=result,
                competition_key=comp.key,
                league_id=comp.league_id,
                season=season,
                fixture_id=fid,
            )
        return [i for i in items if isinstance(i, dict)]

    def _ingest_fixture_details(
        self,
        item: dict[str, Any],
        comp: CompetitionConfig,
        season: int,
        result: EgieIngestRunResult,
    ) -> None:
        fixture_id = self._extract_fixture_id(item)
        if fixture_id is None:
            return

        status_short = str(((item.get("fixture") or {}).get("status") or {}).get("short") or "")
        if status_short not in _FINISHED_STATUSES:
            return

        league_id = int((item.get("league") or {}).get("id") or comp.league_id)

        endpoints: list[tuple[str, str, dict[str, Any], Any]] = [
            (
                "events",
                "fixtures/events",
                {"fixture": fixture_id},
                self.client.get_fixture_events(fixture_id),
            ),
            (
                "lineups",
                "fixtures/lineups",
                {"fixture": fixture_id},
                self.client.get_fixture_lineups(fixture_id),
            ),
            (
                "fixture_statistics",
                "fixtures/statistics",
                {"fixture": fixture_id},
                self.client.get_fixture_statistics(fixture_id),
            ),
            (
                "injuries",
                "injuries",
                {"fixture": fixture_id, "league": league_id, "season": season},
                self.client.get_injuries(fixture_id, league_id=league_id, season=season),
            ),
        ]

        for resource_type, endpoint, params, call in endpoints:
            api = self._track_api(call, result)
            if api.skip_reason:
                continue
            self._save_api_payload(
                resource_type=resource_type,
                request_endpoint=endpoint,
                request_params=params,
                api_result=api,
                result=result,
                competition_key=comp.key,
                league_id=league_id,
                season=season,
                fixture_id=fixture_id,
            )

    @staticmethod
    def _extract_fixture_id(item: dict[str, Any]) -> int | None:
        fixture = item.get("fixture") or {}
        try:
            fid = int(fixture.get("id") or 0)
        except (TypeError, ValueError):
            return None
        return fid if fid > 0 else None
