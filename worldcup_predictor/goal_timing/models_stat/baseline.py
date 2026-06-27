"""Baseline statistical model for goal timing (Phase 51D)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES
from worldcup_predictor.goal_timing.minute_ranges import counts_to_probabilities
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput

from worldcup_predictor.goal_timing.minute_display import (
    bucket_representative_minute,
    display_estimated_first_goal_minute,
    weighted_average_minute,
)
from worldcup_predictor.goal_timing.bucket_selection import pick_goal_time_range

AGENT_RANGE_WEIGHTS: dict[str, float] = {
    "goal_timing_pattern": 0.40,
    "first_goal_pressure": 0.15,
    "tactical_goal_flow": 0.10,
    "player_goal_threat": 0.10,
    "motivation_goal": 0.05,
}


class GoalTimingBaselineModel:
    """Empirical baseline using team/league minute distributions and agent signals."""

    def predict(
        self,
        features: dict[str, Any],
        agent_outputs: dict[str, GoalTimingAgentOutput],
    ) -> dict[str, Any]:
        home_team = str(features.get("home_team") or "Home")
        away_team = str(features.get("away_team") or "Away")

        home_range = self._team_range_prior(features, side="home")
        away_range = self._team_range_prior(features, side="away")
        league_range = self._league_range_prior(features)

        blended_match = self._blend_dicts(
            [home_range, away_range, league_range],
            weights=[0.40, 0.40, 0.20],
        )
        agent_shift = self._agent_range_shift(agent_outputs)
        match_range = self._normalize(self._blend_dicts([blended_match, agent_shift], weights=[0.85, 0.15]))

        first_goal_team = self._pick_first_goal_team(features, agent_outputs)
        first_goal_time_range, bucket_is_default, bucket_reason = pick_goal_time_range(match_range)
        wavg = weighted_average_minute(match_range)
        bucket_minute = bucket_representative_minute(first_goal_time_range) if first_goal_time_range else None
        display_minute = (
            display_estimated_first_goal_minute(first_goal_time_range) if first_goal_time_range else None
        )

        home_scored = self._team_scoring_range(features, side="home")
        away_scored = self._team_scoring_range(features, side="away")

        no_goal_probs = self._no_goal_curve(features)

        dq = float(features.get("data_quality_score") or 0.0)
        pattern = agent_outputs.get("goal_timing_pattern")
        pattern_impact = float(pattern.impact_score if pattern and pattern.impact_score is not None else 0.35)
        raw_confidence = min(0.88, 0.25 + dq * 0.45 + pattern_impact * 0.25)

        return {
            "first_goal_team": first_goal_team,
            "first_goal_time_range": first_goal_time_range,
            "bucket_is_default": bucket_is_default,
            "bucket_reason": bucket_reason,
            "bucket_source": "fallback" if bucket_is_default else "model_output",
            "weighted_average_minute": wavg,
            "bucket_representative_minute": bucket_minute,
            "display_estimated_first_goal_minute": display_minute,
            "home_range_probs": home_scored,
            "away_range_probs": away_scored,
            "match_first_goal_range_probs": match_range,
            "no_goal_probs": no_goal_probs,
            "raw_confidence": round(raw_confidence, 4),
            "home_team": home_team,
            "away_team": away_team,
        }

    def _team_range_prior(self, features: dict[str, Any], *, side: str) -> dict[str, float]:
        dist = (features.get("first_goal_minute_distribution") or {}).get(side) or {}
        if any(float(dist.get(k) or 0) > 0 for k in GOAL_TIMING_MINUTE_RANGES):
            return self._normalize({k: float(dist.get(k) or 0.0) for k in GOAL_TIMING_MINUTE_RANGES})
        scored = (features.get("team_goals_scored_by_range") or {}).get(side) or {}
        return counts_to_probabilities({k: int(float(scored.get(k) or 0)) for k in GOAL_TIMING_MINUTE_RANGES})

    def _team_scoring_range(self, features: dict[str, Any], *, side: str) -> dict[str, float]:
        scored = (features.get("team_goals_scored_by_range") or {}).get(side) or {}
        return counts_to_probabilities({k: int(float(scored.get(k) or 0)) for k in GOAL_TIMING_MINUTE_RANGES})

    def _league_range_prior(self, features: dict[str, Any]) -> dict[str, float]:
        dist = (features.get("first_goal_minute_distribution") or {}).get("league") or {}
        if any(float(dist.get(k) or 0) > 0 for k in GOAL_TIMING_MINUTE_RANGES):
            return self._normalize({k: float(dist.get(k) or 0.0) for k in GOAL_TIMING_MINUTE_RANGES})
        base = features.get("league_baseline_timing") or {}
        dist2 = base.get("first_goal_minute_distribution") or {}
        return counts_to_probabilities({k: int(float(dist2.get(k) or 0)) for k in GOAL_TIMING_MINUTE_RANGES})

    def _pick_first_goal_team(
        self,
        features: dict[str, Any],
        agent_outputs: dict[str, GoalTimingAgentOutput],
    ) -> str:
        home_fg = (features.get("first_goal_team_distribution") or {}).get("home") or {}
        away_fg = (features.get("first_goal_team_distribution") or {}).get("away") or {}
        home_rate = float(home_fg.get("scored_first") or 0.33)
        away_rate = float(away_fg.get("scored_first") or 0.33)

        pressure = agent_outputs.get("first_goal_pressure")
        if pressure and pressure.signals.get("pressure_edge") == "home":
            home_rate += 0.05
        elif pressure and pressure.signals.get("pressure_edge") == "away":
            away_rate += 0.05

        threat = agent_outputs.get("player_goal_threat")
        if threat:
            share = float(threat.signals.get("home_scoring_share") or 0.5)
            home_rate += (share - 0.5) * 0.15
            away_rate += (0.5 - share) * 0.15

        tactical = agent_outputs.get("tactical_goal_flow")
        if tactical:
            flow = float(tactical.signals.get("combined_flow_edge") or 0.0)
            if flow > 0:
                home_rate += 0.04
            elif flow < 0:
                away_rate += 0.04

        if abs(home_rate - away_rate) < 0.04:
            return "none"
        return "home" if home_rate > away_rate else "away"

    def _agent_range_shift(self, agent_outputs: dict[str, GoalTimingAgentOutput]) -> dict[str, float]:
        uniform = 1.0 / len(GOAL_TIMING_MINUTE_RANGES)
        out = {k: uniform for k in GOAL_TIMING_MINUTE_RANGES}
        pattern = agent_outputs.get("goal_timing_pattern")
        if not pattern:
            return out
        home_dom = pattern.signals.get("home_dominant_range")
        away_dom = pattern.signals.get("away_dominant_range")
        for dom in (home_dom, away_dom):
            if dom in GOAL_TIMING_MINUTE_RANGES:
                out[dom] += 0.08
        return self._normalize(out)

    def _no_goal_curve(self, features: dict[str, Any]) -> dict[str, float]:
        league = (features.get("no_goal_before_minute_probability") or {}).get("league") or {}
        if league:
            return {k: float(v) for k, v in league.items()}
        n = len(GOAL_TIMING_MINUTE_RANGES)
        return {r: round(1.0 - (i + 1) / n, 4) for i, r in enumerate(GOAL_TIMING_MINUTE_RANGES)}

    @staticmethod
    def _normalize(dist: dict[str, float]) -> dict[str, float]:
        total = sum(max(0.0, float(dist.get(k) or 0.0)) for k in GOAL_TIMING_MINUTE_RANGES)
        if total <= 0:
            uniform = round(1.0 / len(GOAL_TIMING_MINUTE_RANGES), 4)
            return {k: uniform for k in GOAL_TIMING_MINUTE_RANGES}
        return {k: round(max(0.0, float(dist.get(k) or 0.0)) / total, 4) for k in GOAL_TIMING_MINUTE_RANGES}

    @staticmethod
    def _blend_dicts(dicts: list[dict[str, float]], *, weights: list[float]) -> dict[str, float]:
        out = {k: 0.0 for k in GOAL_TIMING_MINUTE_RANGES}
        weight_sum = sum(weights) or 1.0
        for dist, w in zip(dicts, weights):
            for k in GOAL_TIMING_MINUTE_RANGES:
                out[k] += float(dist.get(k) or 0.0) * (w / weight_sum)
        return out
