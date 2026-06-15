from __future__ import annotations

from dataclasses import dataclass

from worldcup_predictor.agents.base import AgentContext, AgentResult
from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
from worldcup_predictor.agents.fixture_agent import FixtureAgent
from worldcup_predictor.agents.prediction_agent import PredictionAgent
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.domain.fixture import FixtureCollection
from worldcup_predictor.domain.prediction import PredictionPlaceholder


@dataclass
class UpcomingPipelineResult:
    fixtures: FixtureCollection
    predictions: list[PredictionPlaceholder]
    agent_results: list[AgentResult]
    success: bool


class UpcomingPipeline:
    """Orchestrates Fixture → DataCollector → Prediction agents."""

    def __init__(self, settings: Settings, *, competition_key: str = "world_cup_2026", locale: str = "en") -> None:
        self._settings = settings
        self._competition_key = competition_key
        self._locale = locale

    def run(self, limit: int | None = None) -> UpcomingPipelineResult:
        context = AgentContext(
            settings=self._settings,
            competition_key=self._competition_key,
            locale=self._locale,
        )

        fixture_limit = limit or self._settings.upcoming_fixture_limit
        agents = [
            FixtureAgent(context),
            DataCollectorAgent(context),
            PredictionAgent(context),
        ]

        results: list[AgentResult] = []
        for agent in agents:
            if isinstance(agent, FixtureAgent):
                result = agent.run(limit=fixture_limit)
            else:
                result = agent.run()
            results.append(result)
            if not result.success:
                return UpcomingPipelineResult(
                    fixtures=context.shared.get("fixtures") or FixtureCollection(),
                    predictions=context.shared.get("predictions") or [],
                    agent_results=results,
                    success=False,
                )

        return UpcomingPipelineResult(
            fixtures=context.shared["fixtures"],
            predictions=context.shared["predictions"],
            agent_results=results,
            success=True,
        )
