from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.agents._helpers import feature_agent_output
from worldcup_predictor.goal_timing.agents.base import GoalTimingAgentBase
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


class OddsGoalIntelligenceAgent(GoalTimingAgentBase):
    name = "odds_goal_intelligence"

    def analyze(self, fixture_id: int, *, features: dict[str, Any], context: dict[str, Any]) -> GoalTimingAgentOutput:
        reliable = bool(features.get("has_reliable_goal_odds"))
        return feature_agent_output(
            self.name,
            features=features,
            signals={"reliable_odds": reliable, "focus": "goal_timing_odds"},
            impact_score=0.6 if reliable else 0.15,
            missing=[] if reliable else ["goal_market_odds"],
            notes="Goal-market odds not available in Phase 51D baseline.",
        )
