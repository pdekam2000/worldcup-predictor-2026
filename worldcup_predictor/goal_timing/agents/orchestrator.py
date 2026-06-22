"""Goal timing specialist agent orchestrator."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.agents.data_quality import DataQualityGoalAgent
from worldcup_predictor.goal_timing.agents.first_goal_pressure import FirstGoalPressureAgent
from worldcup_predictor.goal_timing.agents.goal_timing_pattern import GoalTimingPatternAgent
from worldcup_predictor.goal_timing.agents.lineup_goal_impact import LineupGoalImpactAgent
from worldcup_predictor.goal_timing.agents.motivation_goal import MotivationGoalAgent
from worldcup_predictor.goal_timing.agents.odds_goal_intelligence import OddsGoalIntelligenceAgent
from worldcup_predictor.goal_timing.agents.player_goal_threat import PlayerGoalThreatAgent
from worldcup_predictor.goal_timing.agents.tactical_goal_flow import TacticalGoalFlowAgent
from worldcup_predictor.goal_timing.config import GOAL_TIMING_AGENT_KEYS
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


class GoalTimingAgentOrchestrator:
    def __init__(self) -> None:
        self._agents = (
            GoalTimingPatternAgent(),
            FirstGoalPressureAgent(),
            LineupGoalImpactAgent(),
            PlayerGoalThreatAgent(),
            TacticalGoalFlowAgent(),
            OddsGoalIntelligenceAgent(),
            MotivationGoalAgent(),
            DataQualityGoalAgent(),
        )

    @property
    def agent_keys(self) -> tuple[str, ...]:
        return GOAL_TIMING_AGENT_KEYS

    def run(
        self,
        fixture_id: int,
        *,
        features: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, GoalTimingAgentOutput]:
        out: dict[str, GoalTimingAgentOutput] = {}
        for agent in self._agents:
            result = agent.analyze(fixture_id, features=features, context=context)
            out[agent.name] = result
        return out
