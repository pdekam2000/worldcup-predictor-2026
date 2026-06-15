from __future__ import annotations

from dataclasses import dataclass

from worldcup_predictor.agents.base import AgentContext, AgentResult
from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.domain.specialist import MatchSpecialistReport


@dataclass
class SpecialistsPipelineResult:
    report: MatchSpecialistReport
    agent_results: list[AgentResult]
    success: bool


class SpecialistsPipeline:
    """Collect intelligence then run all specialist agents."""

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

    def run(self, fixture_id: int) -> SpecialistsPipelineResult:
        context = AgentContext(
            settings=self._settings,
            competition_key=self._competition_key,
            locale=self._locale,
        )
        results: list[AgentResult] = []

        collector = DataCollectorAgent(context)
        collect_result = collector.run(fixture_id=fixture_id)
        results.append(collect_result)
        if not collect_result.success:
            return SpecialistsPipelineResult(
                report=_empty_report(fixture_id),
                agent_results=results,
                success=False,
            )

        orchestrator = SpecialistOrchestrator(context)
        specialist_result = orchestrator.run(fixture_id=fixture_id)
        results.append(specialist_result)

        if not specialist_result.success or not isinstance(specialist_result.data, MatchSpecialistReport):
            return SpecialistsPipelineResult(
                report=_empty_report(fixture_id),
                agent_results=results,
                success=False,
            )

        return SpecialistsPipelineResult(
            report=specialist_result.data,
            agent_results=results,
            success=True,
        )


def _empty_report(fixture_id: int) -> MatchSpecialistReport:
    return MatchSpecialistReport(fixture_id=fixture_id)
