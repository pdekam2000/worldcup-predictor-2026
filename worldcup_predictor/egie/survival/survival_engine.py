"""Shadow-mode Survival EGIE engine — does not replace production EliteGoalTimingEngine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from worldcup_predictor.egie.survival.config import SURVIVAL_MODEL_VERSION
from worldcup_predictor.egie.survival.hazard_model import hazard_curve_from_km
from worldcup_predictor.egie.survival.kaplan_meier import fit_kaplan_meier
from worldcup_predictor.egie.survival.range_probability_model import (
    pick_primary_range,
    range_probabilities_from_profiles,
)
from worldcup_predictor.egie.survival.team_first_goal_survival import (
    pick_team_with_abstain,
    team_first_goal_probabilities,
)
from worldcup_predictor.egie.survival.team_survival_profiles import TeamSurvivalProfileStore
from worldcup_predictor.goal_timing.agents.orchestrator import GoalTimingAgentOrchestrator
from worldcup_predictor.goal_timing.confidence import GoalTimingConfidenceEngine
from worldcup_predictor.goal_timing.calibration import GoalTimingCalibrator
from worldcup_predictor.goal_timing.config import MIN_DATA_QUALITY_FOR_PREDICTION
from worldcup_predictor.goal_timing.data.stored_adapter import HistoricalMatchContext, StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
from worldcup_predictor.goal_timing.leagues import is_goal_timing_prediction_league
from worldcup_predictor.goal_timing.minute_display import display_estimated_first_goal_minute
from worldcup_predictor.goal_timing.minute_ranges import effective_minute
from worldcup_predictor.goal_timing.models_stat.baseline import GoalTimingBaselineModel


def _league_observations(matches: list[HistoricalMatchContext]) -> list[tuple[float, int]]:
    obs: list[tuple[float, int]] = []
    for ctx in matches:
        minute = ctx.first_goal_minute
        if ctx.goal_events:
            first = ctx.goal_events[0]
            minute = effective_minute(first.minute, first.extra_minute)
        if minute is None and not ctx.goal_events:
            obs.append((90.0, 0))
        elif minute is not None:
            obs.append((float(minute), 1))
    return obs


def _compute_rates(features: dict[str, Any], agent_outputs: dict[str, Any]) -> tuple[float, float]:
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
    return home_rate, away_rate


class SurvivalGoalTimingEngine:
    """Statistical survival layer for goal timing (shadow / backtest only)."""

    def __init__(
        self,
        *,
        stored: StoredGoalTimingAdapter | None = None,
        feature_builder: GoalTimingFeatureBuilder | None = None,
    ) -> None:
        self.stored = stored or StoredGoalTimingAdapter()
        self.feature_builder = feature_builder or GoalTimingFeatureBuilder(
            stored=self.stored,
            max_api_event_fetches=0,
        )
        self.agents = GoalTimingAgentOrchestrator()
        self.baseline = GoalTimingBaselineModel()
        self.calibrator = GoalTimingCalibrator()
        self.confidence_engine = GoalTimingConfidenceEngine()
        self.profiles = TeamSurvivalProfileStore(stored=self.stored)

    def predict_fixture(
        self,
        fixture_id: int,
        *,
        competition_key: str | None = None,
        as_of: datetime | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        target = self.feature_builder.stored.get_target_fixture(fixture_id)
        comp_key = competition_key or str((target or {}).get("competition_key") or "premier_league")
        kickoff_raw = (target or {}).get("kickoff_utc") or ctx.get("match_date")
        as_of_dt = as_of or self.stored.parse_kickoff(kickoff_raw) or datetime.utcnow()
        before_iso = kickoff_raw or as_of_dt.isoformat()

        home_team = str(ctx.get("home_team") or (target or {}).get("home_team") or "Home")
        away_team = str(ctx.get("away_team") or (target or {}).get("away_team") or "Away")

        features = self.feature_builder.build(
            fixture_id,
            competition_key=comp_key,
            as_of=as_of_dt,
            context={**ctx, "home_team": home_team, "away_team": away_team, "match_date": as_of_dt},
        )
        agent_outputs = self.agents.run(
            fixture_id,
            features=features,
            context={**ctx, "home_team": home_team, "away_team": away_team, "match_date": as_of_dt},
        )
        home_rate, away_rate = _compute_rates(features, agent_outputs)
        raw = self.baseline.predict(features, agent_outputs)
        calibrated = self.calibrator.calibrate(raw)
        confidence, data_quality, _model_conf = self.confidence_engine.score(
            features, agent_outputs, calibrated
        )
        dq = float(data_quality)
        league_ok = is_goal_timing_prediction_league(comp_key)
        no_prediction = (not league_ok) or dq < MIN_DATA_QUALITY_FOR_PREDICTION

        league_history = self.stored.league_history_before(
            before_kickoff=before_iso,
            competition_key=comp_key,
            limit=400,
        )
        league_km = fit_kaplan_meier(_league_observations(league_history))
        survival_curve = league_km["survival_curve"]

        team_profiles = self.profiles.build_profiles(
            before_kickoff=before_iso,
            competition_keys=[comp_key],
        )
        home_prof = (team_profiles.get(home_team) or {}).get("home_profile") or {}
        away_prof = (team_profiles.get(away_team) or {}).get("away_profile") or {}

        range_probs = range_probabilities_from_profiles(
            league_survival_curve=survival_curve,
            home_profile=home_prof,
            away_profile=away_prof,
        )
        hazard = hazard_curve_from_km(survival_curve)
        team_probs = team_first_goal_probabilities(
            home_rate=home_rate,
            away_rate=away_rate,
            league_survival_curve=survival_curve,
            range_probs=range_probs,
        )
        team_pick = pick_team_with_abstain(team_probs)
        primary_range = pick_primary_range(range_probs)
        display_minute = display_estimated_first_goal_minute(primary_range)

        return {
            "fixture_id": fixture_id,
            "competition_key": comp_key,
            "home_team": home_team,
            "away_team": away_team,
            "model_version": SURVIVAL_MODEL_VERSION,
            "shadow_mode": True,
            "no_prediction_flag": no_prediction,
            "data_quality_score": dq,
            "confidence_score": confidence,
            "first_goal_team": team_pick,
            "first_goal_time_range": primary_range,
            "display_estimated_first_goal_minute": display_minute,
            "range_probabilities": range_probs,
            "team_probabilities": team_probs,
            "survival_curve": survival_curve,
            "checkpoint_goal_probability": league_km["checkpoint_goal_probability"],
            "hazard_curve": hazard,
            "home_goal_rate": round(home_rate, 4),
            "away_goal_rate": round(away_rate, 4),
        }
