from __future__ import annotations

from dataclasses import dataclass

from worldcup_predictor.agents.base import AgentContext, AgentResult
from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport, TeamIntelligence


@dataclass
class InspectPipelineResult:
    report: MatchIntelligenceReport
    agent_results: list[AgentResult]
    success: bool


class InspectPipeline:
    """Single-fixture intelligence collection for CLI inspect command."""

    def __init__(
        self,
        settings: Settings,
        *,
        competition_key: str = "world_cup_2026",
        locale: str = "en",
    ) -> None:
        self._settings = settings
        self._competition_key = competition_key
        self._locale = locale

    def run(self, fixture_id: int) -> InspectPipelineResult:
        context = AgentContext(
            settings=self._settings,
            competition_key=self._competition_key,
            locale=self._locale,
        )
        collector = DataCollectorAgent(context)
        result = collector.run(fixture_id=fixture_id)

        if not result.success or not isinstance(result.data, MatchIntelligenceReport):
            return InspectPipelineResult(
                report=MatchIntelligenceReport(
                    fixture_id=fixture_id,
                    fixture=None,
                    home_team=TeamIntelligence(team_name="Unknown"),
                    away_team=TeamIntelligence(team_name="Unknown"),
                ),
                agent_results=[result],
                success=False,
            )

        return InspectPipelineResult(
            report=result.data,
            agent_results=[result],
            success=True,
        )
