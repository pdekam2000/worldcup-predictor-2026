from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.domain.fixture import Fixture, FixtureCollection
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport


class DataCollectorAgent(BaseAgent):
    """
    Collects supplementary match intelligence for each fixture.

    Phase 2: team form, H2H, injuries, stats, lineups, odds snapshot,
    missing_data tracking, and data_quality_score.
    """

    name = "data_collector_agent"

    def __init__(
        self,
        context,
        api_client: ApiFootballClient | None = None,
        builder: MatchIntelligenceBuilder | None = None,
    ) -> None:
        super().__init__(context)
        self._api = api_client or ApiFootballClient(context.settings)
        self._builder = builder or MatchIntelligenceBuilder(self._api)

    def run(self, **kwargs: Any) -> AgentResult:
        fixture_id = kwargs.get("fixture_id")

        if fixture_id is not None:
            if self.context.shared.get("smart_prediction_fetch"):
                from worldcup_predictor.quota.smart_prediction_fetch import SmartPredictionFetcher

                report = SmartPredictionFetcher(self._api, self._builder).build(int(fixture_id))
            else:
                report = self._builder.build_by_fixture_id(int(fixture_id))
            self.context.shared["intelligence_reports"] = {report.fixture_id: report}
            self.context.shared["collected_data"] = {
                report.fixture_id: self._legacy_summary(report),
            }
            return self._ok(
                data=report,
                message=f"Collected intelligence for fixture {fixture_id}",
            )

        collection: FixtureCollection | None = self.context.shared.get("fixtures")
        if collection is None:
            return self._fail("No fixtures in context. Run FixtureAgent first.")

        reports: dict[int, MatchIntelligenceReport] = {}
        collected: dict[int, dict[str, Any]] = {}

        for fixture in collection.fixtures:
            report = self._builder.build(fixture)
            reports[fixture.id] = report
            collected[fixture.id] = self._legacy_summary(report)

        self.context.shared["intelligence_reports"] = reports
        self.context.shared["collected_data"] = collected
        return self._ok(
            data=reports,
            message=f"Collected intelligence for {len(reports)} fixtures",
        )

    @staticmethod
    def _legacy_summary(report: MatchIntelligenceReport) -> dict[str, Any]:
        """Backward-compatible shape for Phase 1 PredictionAgent."""
        return {
            "fixture_id": report.fixture_id,
            "home_team": report.home_team.team_name,
            "away_team": report.away_team.team_name,
            "team_form": {
                "home": report.home_team.form,
                "away": report.away_team.form,
            },
            "head_to_head": report.head_to_head,
            "injuries": {
                "home": (report.home_team.injuries.players if report.home_team.injuries else []),
                "away": (report.away_team.injuries.players if report.away_team.injuries else []),
            },
            "lineups_available": bool(report.lineups and report.lineups.get("available")),
            "fixture_statistics": report.fixture_statistics,
            "odds_snapshot": report.odds,
            "missing_data": report.missing_data,
            "data_quality_score": report.data_quality.score if report.data_quality else 0.0,
            "source": report.source,
            "ready_for_prediction": report.ready_for_prediction,
        }
