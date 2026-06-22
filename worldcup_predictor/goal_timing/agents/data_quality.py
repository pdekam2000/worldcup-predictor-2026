from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.agents.base import GoalTimingAgentBase
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


class DataQualityGoalAgent(GoalTimingAgentBase):
    name = "data_quality"

    def analyze(self, fixture_id: int, *, features: dict[str, Any], context: dict[str, Any]) -> GoalTimingAgentOutput:
        manifest = features.get("provider_manifest") or {}
        available = sum(1 for v in manifest.values() if v)
        total = max(len(manifest), 1)
        coverage = available / total
        missing = [k for k, v in manifest.items() if not v] if manifest else ["provider_manifest"]
        return GoalTimingAgentOutput(
            agent_name=self.name,
            status="available" if coverage >= 0.4 else "limited",
            signals={"coverage_ratio": round(coverage, 3), "available_sources": available},
            impact_score=coverage,
            missing_data=missing,
            notes="Scores input reliability for no-prediction gates.",
        )
