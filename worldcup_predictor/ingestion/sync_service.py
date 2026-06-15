"""Sync real API fixture/result data into SQLite."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from worldcup_predictor.config.competitions import get_competition, list_competition_keys
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.schedule.competition_schedule import create_schedule_service
from worldcup_predictor.schedule.match_center import classify_status

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    competition_key: str
    fixtures_synced: int = 0
    results_synced: int = 0
    odds_snapshots: int = 0
    xg_snapshots: int = 0
    skipped_placeholder: int = 0
    warnings: list[str] = field(default_factory=list)


class DataSyncService:
    """Pull upcoming/live/finished fixtures from API-Sports and persist to DB."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        repository: FootballIntelligenceRepository | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._repo = repository or FootballIntelligenceRepository()
        self._repo.seed_competitions()

    def sync_competition(self, competition_key: str, *, enrich: bool = True) -> SyncResult:
        comp = get_competition(competition_key)
        self._repo.upsert_competition(comp)
        result = SyncResult(competition_key=comp.key)

        if not comp.league_id_configured:
            result.warnings.append(f"{comp.key}: league_id not configured — skipped.")
            return result

        schedule = create_schedule_service(self._settings, competition_key=comp.key)
        try:
            fixtures = schedule.get_all_worldcup_fixtures()
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"API fetch failed: {exc}")
            return result

        for fixture in fixtures:
            if fixture.is_placeholder or fixture.source == "placeholder":
                result.skipped_placeholder += 1
                continue
            if self._repo.upsert_fixture(fixture, competition_key=comp.key):
                result.fixtures_synced += 1
            if classify_status(fixture.status) == "finished":
                if self._repo.upsert_fixture_result(fixture, competition_key=comp.key):
                    result.results_synced += 1
            if enrich:
                self._enrich_fixture(fixture, comp.key, result)

        return result

    def sync_all_active(self) -> list[SyncResult]:
        results: list[SyncResult] = []
        for key in list_competition_keys():
            comp = get_competition(key)
            if comp.league_id_configured:
                results.append(self.sync_competition(key))
        return results

    def _enrich_fixture(self, fixture: TournamentFixture, competition_key: str, result: SyncResult) -> None:
        """Save odds/xG snapshots when RapidAPI enrichment is available."""
        try:
            from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
            from worldcup_predictor.clients.api_football import ApiFootballClient

            builder = MatchIntelligenceBuilder(ApiFootballClient(self._settings))
            report = builder.build_by_fixture_id(fixture.fixture_id)
            supplemental = getattr(report, "supplemental_sources", None) or {}

            payload: dict[str, Any] = {
                "snapshot_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            }
            if report.odds and report.odds.available and report.odds.bookmakers:
                payload["api_sports"] = {"bookmakers": report.odds.bookmakers}
            if supplemental.get("rapid_football_stats"):
                payload["rapid_football_stats"] = supplemental["rapid_football_stats"]
            if supplemental.get("rapid_xg_statistics"):
                payload["rapid_xg_statistics"] = supplemental["rapid_xg_statistics"]
            odds_payload = supplemental.get("the_odds_api") or supplemental.get("odds") or {}
            if odds_payload:
                payload["the_odds_api"] = odds_payload if isinstance(odds_payload, dict) else {"raw": odds_payload}

            if len(payload) > 1:
                self._repo.save_snapshot(
                    "odds_snapshots",
                    fixture_id=fixture.fixture_id,
                    competition_key=competition_key,
                    payload=payload,
                )
                result.odds_snapshots += 1

            rapid_xg = supplemental.get("rapid_xg_statistics") or {}
            rapid_stats = supplemental.get("rapid_football_stats") or {}
            xg_payload = {k: v for k, v in {"rapid_xg": rapid_xg, "rapid_stats": rapid_stats}.items() if v}
            if xg_payload:
                self._repo.save_snapshot(
                    "xg_snapshots",
                    fixture_id=fixture.fixture_id,
                    competition_key=competition_key,
                    payload=xg_payload,
                )
                result.xg_snapshots += 1

            if report.specialist_report:
                self._repo.save_snapshot(
                    "agent_signals",
                    fixture_id=fixture.fixture_id,
                    competition_key=competition_key,
                    payload={"specialists": True},
                    agent_name="specialists",
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Enrichment skipped for fixture %s: %s", fixture.fixture_id, exc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
