from __future__ import annotations

from dataclasses import dataclass

from worldcup_predictor.agents.base import AgentContext, AgentResult
from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
from worldcup_predictor.agents.prediction_agent import PredictionAgent
from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.schedule.context_loader import load_tournament_context


@dataclass
class AuditPipelineResult:
    prediction: MatchPrediction
    agent_results: list[AgentResult]
    success: bool


class AuditPipeline:
    """Full pipeline with weighted decision + auditable prediction output."""

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

    def run(self, fixture_id: int) -> AuditPipelineResult:
        context = AgentContext(
            settings=self._settings,
            competition_key=self._competition_key,
            locale=self._locale,
        )
        load_tournament_context(context)
        results: list[AgentResult] = []

        collector = DataCollectorAgent(context)
        collect_result = collector.run(fixture_id=fixture_id)
        results.append(collect_result)
        if not collect_result.success:
            return AuditPipelineResult(
                prediction=_empty_prediction(fixture_id),
                agent_results=results,
                success=False,
            )

        specialist = SpecialistOrchestrator(context)
        specialist_result = specialist.run(fixture_id=fixture_id)
        results.append(specialist_result)

        predictor = PredictionAgent(context)
        predict_result = predictor.run(fixture_id=fixture_id)
        results.append(predict_result)

        if not predict_result.success or not isinstance(predict_result.data, MatchPrediction):
            return AuditPipelineResult(
                prediction=_empty_prediction(fixture_id),
                agent_results=results,
                success=False,
            )

        return AuditPipelineResult(
            prediction=predict_result.data,
            agent_results=results,
            success=True,
        )


def _empty_prediction(fixture_id: int) -> MatchPrediction:
    from worldcup_predictor.orchestration.predict_pipeline import _empty_prediction as empty

    return empty(fixture_id)
