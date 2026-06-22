"""Confidence and data quality scoring."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.minute_display import cap_display_confidence
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


class GoalTimingConfidenceEngine:
    def score(
        self,
        features: dict[str, Any],
        agent_outputs: dict[str, GoalTimingAgentOutput],
        calibrated: dict[str, Any],
    ) -> tuple[float, float, float]:
        """
        Returns (display_confidence_score, data_quality_score, model_confidence_score).
        Display confidence is capped when data quality is below threshold.
        """
        dq_agent = agent_outputs.get("data_quality")
        data_quality = float(dq_agent.impact_score if dq_agent and dq_agent.impact_score is not None else 0.35)

        manifest = features.get("provider_manifest") or {}
        if manifest:
            coverage = sum(1 for v in manifest.values() if v) / max(len(manifest), 1)
            data_quality = round((data_quality + coverage) / 2, 4)

        model_confidence = float(calibrated.get("calibrated_confidence") or calibrated.get("raw_confidence") or 0.4)
        model_confidence = round(min(model_confidence, data_quality + 0.25), 4)
        display_confidence = cap_display_confidence(model_confidence, data_quality)
        return display_confidence, data_quality, model_confidence
