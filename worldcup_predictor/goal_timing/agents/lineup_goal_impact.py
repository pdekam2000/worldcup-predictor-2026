from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.agents._helpers import feature_agent_output
from worldcup_predictor.goal_timing.agents.base import GoalTimingAgentBase
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


class LineupGoalImpactAgent(GoalTimingAgentBase):
    name = "lineup_goal_impact"

    def analyze(self, fixture_id: int, *, features: dict[str, Any], context: dict[str, Any]) -> GoalTimingAgentOutput:
        manifest = features.get("provider_manifest") or {}
        has_lineups = bool(context.get("has_lineups") or manifest.get("expected_lineups"))
        impact = 0.55 if has_lineups else 0.25
        return feature_agent_output(
            self.name,
            features=features,
            signals={"lineups_available": has_lineups, "focus": "striker_creator_gk_availability"},
            impact_score=impact,
            missing=[] if has_lineups else ["expected_lineups"],
            notes="Lineup intelligence not wired in Phase 51D — historical timing only.",
        )
