from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.agents._helpers import feature_agent_output
from worldcup_predictor.goal_timing.agents.base import GoalTimingAgentBase
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


class LineupGoalImpactAgent(GoalTimingAgentBase):
    name = "lineup_goal_impact"

    def analyze(self, fixture_id: int, *, features: dict[str, Any], context: dict[str, Any]) -> GoalTimingAgentOutput:
        strategy = str(features.get("paid_provider_strategy") or "production")
        pf = features.get("provider_features") or {}
        lh = pf.get("lineup_strength_home")
        la = pf.get("lineup_strength_away")
        if strategy == "F" and (lh is not None or la is not None):
            return feature_agent_output(
                self.name,
                features=features,
                signals={
                    "lineups_available": True,
                    "lineup_strength_home": lh,
                    "lineup_strength_away": la,
                    "lineup_edge": "home" if (lh or 0) > (la or 0) else "away",
                },
                impact_score=min(1.0, 0.45 + abs((lh or 0) - (la or 0))),
                missing=[],
                notes="Lineup strength from API-Football EGIE raw store.",
            )

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
