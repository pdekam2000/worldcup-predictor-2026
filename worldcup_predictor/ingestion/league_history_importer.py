"""Phase 39B — Import API-Football league history into SQLite."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import CompetitionConfig, get_competition
from worldcup_predictor.config.league_registry import (
    list_enabled_european_leagues,
    resolve_competition_by_league_id,
)
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.integrations.fixture_api_parser import FINISHED_STATUSES, parse_api_fixture_item

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


@dataclass
class LeagueImportResult:
    competition_key: str
    league_id: int
    season: int
    fixtures_imported: int = 0
    fixtures_skipped: int = 0
    enrichment_errors: int = 0
    success: bool = False
    message: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "competition_key": self.competition_key,
            "league_id": self.league_id,
            "season": self.season,
            "fixtures_imported": self.fixtures_imported,
            "fixtures_skipped": self.fixtures_skipped,
            "enrichment_errors": self.enrichment_errors,
            "success": self.success,
            "message": self.message,
            "errors": self.errors,
        }


class LeagueHistoryImporter:
    """Fetch league fixtures and enrichment from API-Football into SQLite."""

    def __init__(
        self,
        settings: Settings | None = None,
        api_client: ApiFootballClient | None = None,
        repository: FootballIntelligenceRepository | None = None,
        *,
        enrich: bool = True,
    ) -> None:
        self._settings = settings or get_settings()
        self._api = api_client or ApiFootballClient(self._settings)
        self._repo = repository or FootballIntelligenceRepository()
        self._enrich = enrich

    @property
    def is_configured(self) -> bool:
        return self._api.is_configured

    def import_league_season(
        self,
        *,
        league_id: int | None = None,
        season: int,
        competition_key: str | None = None,
    ) -> LeagueImportResult:
        comp = self._resolve_competition(league_id=league_id, competition_key=competition_key)
        if comp is None:
            return LeagueImportResult(
                competition_key=competition_key or "unknown",
                league_id=league_id or 0,
                season=season,
                message="Unknown league — not in enabled registry.",
            )

        started = _utc_now()
        run_id = self._repo.start_league_import_run(
            competition_key=comp.key,
            league_id=comp.league_id,
            season=season,
            started_at=started,
        )
        result = LeagueImportResult(
            competition_key=comp.key,
            league_id=comp.league_id,
            season=season,
        )

        existing_ids = self._repo.fixture_ids_for_competition_season(
            competition_key=comp.key,
            season=season,
        )
        sync_state = self._repo.get_league_sync_state(competition_key=comp.key, season=season)
        from_date = (sync_state or {}).get("last_imported_date")

        stored_count = self._repo.count_fixtures_for_league_season(
            competition_key=comp.key,
            season=season,
        )
        if stored_count > 0 and existing_ids and not from_date:
            result.fixtures_skipped = len(existing_ids)
            result.success = True
            result.message = (
                f"Incremental skip — {stored_count} fixtures already in SQLite "
                f"(no new imports; {len(existing_ids)} IDs on file)."
            )
            self._repo.finish_league_import_run(
                run_id,
                status="skipped",
                fixtures_imported=0,
                fixtures_skipped=result.fixtures_skipped,
                enrichment_errors=0,
                message=result.message,
                finished_at=_utc_now(),
            )
            from worldcup_predictor.quota.quota_tracker import get_quota_tracker

            get_quota_tracker().mark_sync()
            return result

        if not self.is_configured:
            return LeagueImportResult(
                competition_key=comp.key,
                league_id=comp.league_id,
                season=season,
                message="API_FOOTBALL_KEY not configured.",
            )

        api_result = self._api.get_historical_fixtures(
            league_id=comp.league_id,
            season=season,
            from_date=from_date,
        )
        if not api_result.ok or not isinstance(api_result.data, list):
            msg = api_result.error or f"No fixtures for league {comp.league_id} season {season}"
            result.message = msg
            result.errors.append(msg)
            self._repo.finish_league_import_run(
                run_id,
                status="failed",
                fixtures_imported=0,
                fixtures_skipped=0,
                enrichment_errors=0,
                message=msg,
                finished_at=_utc_now(),
            )
            return result

        self._repo.upsert_competition(comp)
        profile_key = comp.learning_profile_key or comp.key

        last_fixture_id: int | None = None
        last_fixture_date: str | None = None

        for item in api_result.data:
            fixture = parse_api_fixture_item(item, source="historical")
            if fixture is None:
                result.fixtures_skipped += 1
                continue
            if fixture.fixture_id in existing_ids:
                result.fixtures_skipped += 1
                continue
            saved = self._repo.upsert_fixture(
                fixture,
                competition_key=comp.key,
                league_id=comp.league_id,
                season=season,
            )
            if not saved:
                result.fixtures_skipped += 1
                continue
            if fixture.status in FINISHED_STATUSES:
                self._repo.upsert_fixture_result(fixture, competition_key=comp.key)
            result.fixtures_imported += 1
            existing_ids.add(fixture.fixture_id)
            last_fixture_id = fixture.fixture_id
            if fixture.kickoff_time:
                last_fixture_date = fixture.kickoff_time.date().isoformat()

            if self._enrich and fixture.status in FINISHED_STATUSES:
                err = self._enrich_fixture(
                    fixture.fixture_id,
                    competition_key=comp.key,
                    league_id=comp.league_id,
                    season=season,
                    item=item,
                )
                if err:
                    result.enrichment_errors += 1

        result.success = result.fixtures_imported > 0 or result.fixtures_skipped > 0
        result.message = (
            f"Imported {result.fixtures_imported} fixtures "
            f"(skipped {result.fixtures_skipped}, enrichment errors {result.enrichment_errors})."
        )
        if last_fixture_id is not None or last_fixture_date is not None:
            self._repo.upsert_league_sync_state(
                competition_key=comp.key,
                season=season,
                last_imported_fixture_id=last_fixture_id,
                last_imported_date=last_fixture_date,
                sync_mode="full",
            )
        from worldcup_predictor.quota.quota_tracker import get_quota_tracker

        get_quota_tracker().mark_sync()
        self._repo.finish_league_import_run(
            run_id,
            status="ok" if result.success else "empty",
            fixtures_imported=result.fixtures_imported,
            fixtures_skipped=result.fixtures_skipped,
            enrichment_errors=result.enrichment_errors,
            message=result.message,
            finished_at=_utc_now(),
        )
        _ = profile_key
        return result

    def import_all_enabled(self, *, season: int) -> list[LeagueImportResult]:
        return [
            self.import_league_season(league_id=comp.league_id, season=season)
            for comp in list_enabled_european_leagues()
        ]

    def import_all_enabled_range(
        self,
        *,
        from_season: int,
        to_season: int,
    ) -> list[LeagueImportResult]:
        results: list[LeagueImportResult] = []
        for comp in list_enabled_european_leagues():
            for season in range(from_season, to_season + 1):
                if comp.default_seasons and season not in comp.default_seasons:
                    continue
                results.append(self.import_league_season(league_id=comp.league_id, season=season))
        return results

    def _resolve_competition(
        self,
        *,
        league_id: int | None,
        competition_key: str | None,
    ) -> CompetitionConfig | None:
        if competition_key:
            try:
                return get_competition(competition_key)
            except KeyError:
                return None
        if league_id is not None:
            return resolve_competition_by_league_id(league_id)
        return None

    def _enrich_fixture(
        self,
        fixture_id: int,
        *,
        competition_key: str,
        league_id: int,
        season: int,
        item: dict[str, Any],
    ) -> bool:
        """Best-effort enrichment; returns True if any error occurred."""
        events = item.get("events")
        lineups = None
        statistics = None
        odds = None
        players = None
        had_error = False

        if events is None:
            ev = self._api.get_fixture_events(fixture_id)
            if ev.ok and isinstance(ev.data, list):
                events = ev.data
            elif not ev.ok:
                had_error = True

        lu = self._api.get_fixture_lineups(fixture_id)
        if lu.ok and isinstance(lu.data, list):
            lineups = lu.data
        elif not lu.ok:
            had_error = True

        st = self._api.get_fixture_statistics(fixture_id)
        if st.ok and isinstance(st.data, list):
            statistics = st.data
        elif not st.ok:
            had_error = True

        od = self._api.get_odds(fixture_id)
        if od.ok and od.data:
            odds = od.data
        elif not od.ok:
            had_error = True

        pl = self._api.get_fixture_players(fixture_id)
        if pl.ok and isinstance(pl.data, list):
            players = pl.data

        self._repo.upsert_fixture_enrichment(
            fixture_id=fixture_id,
            competition_key=competition_key,
            league_id=league_id,
            season=season,
            events=events,
            lineups=lineups,
            statistics=statistics,
            players=players,
            odds=odds,
        )
        return had_error
