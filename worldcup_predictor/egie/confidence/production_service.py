"""Attach hybrid confidence to production goal-timing predictions (Phase 52E)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from functools import lru_cache
from typing import Any

from worldcup_predictor.egie.confidence.api_payload import format_hybrid_confidence_api
from worldcup_predictor.egie.confidence.config import (
    TIER_CALIBRATION_PATH,
    VALIDATION_ARTIFACT_PATH,
)
from worldcup_predictor.egie.confidence.hybrid_engine import HybridConfidenceEngine
from worldcup_predictor.egie.confidence.reliability import ReliabilityPriorStore
from worldcup_predictor.egie.confidence.tier_mapper import (
    MarketTierCalibrator,
    TierCalibration,
)
from worldcup_predictor.egie.survival.survival_engine import SurvivalGoalTimingEngine
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.models import GoalTimingPredictionResult

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_calibration_bundle() -> tuple[TierCalibration, MarketTierCalibrator | None, MarketTierCalibrator | None, MarketTierCalibrator | None]:
    tier_cal = TierCalibration(
        team_q25=0.25,
        team_q50=0.45,
        team_q75=0.60,
        range_q25=0.25,
        range_q50=0.45,
        range_q75=0.60,
        minute_q25=0.20,
        minute_q50=0.40,
        minute_q75=0.55,
    )
    if TIER_CALIBRATION_PATH.is_file():
        try:
            raw = json.loads(TIER_CALIBRATION_PATH.read_text(encoding="utf-8"))
            tier_cal = TierCalibration.from_dict(raw)
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    team_cal = range_cal = minute_cal = None
    if VALIDATION_ARTIFACT_PATH.is_file():
        try:
            payload = json.loads(VALIDATION_ARTIFACT_PATH.read_text(encoding="utf-8"))
            iso = payload.get("isotonic_calibrators") or {}
            if iso.get("team"):
                team_cal = MarketTierCalibrator.from_dict(iso["team"])
            if iso.get("range"):
                range_cal = MarketTierCalibrator.from_dict(iso["range"])
            if iso.get("minute"):
                minute_cal = MarketTierCalibrator.from_dict(iso["minute"])
            tc = payload.get("tier_calibration")
            if tc:
                tier_cal = TierCalibration.from_dict(tc)
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.warning("hybrid_confidence_calibration_load_failed: %s", exc)

    return tier_cal, team_cal, range_cal, minute_cal


def _parse_snapshot(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


class HybridConfidenceProductionService:
    """Compute or load hybrid confidence without modifying EliteGoalTimingEngine."""

    def __init__(self, *, stored: StoredGoalTimingAdapter | None = None) -> None:
        self.stored = stored or StoredGoalTimingAdapter()
        self.hybrid_engine = HybridConfidenceEngine()
        self.survival_engine = SurvivalGoalTimingEngine(
            stored=self.stored,
            feature_builder=None,
        )
        self._reliability = ReliabilityPriorStore()

    def compute_snapshot(
        self,
        result: GoalTimingPredictionResult,
        *,
        features: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if result.no_prediction_flag:
            return None

        tier_cal, team_cal, range_cal, minute_cal = _load_calibration_bundle()
        ctx = context or {}
        match_date = result.match_date or ctx.get("match_date")
        if isinstance(match_date, str):
            match_date = self.stored.parse_kickoff(match_date)
        as_of = match_date if isinstance(match_date, datetime) else None

        survival = self.survival_engine.predict_fixture(
            int(result.fixture_id),
            competition_key=result.competition_key,
            as_of=as_of,
            context={
                **ctx,
                "home_team": result.home_team,
                "away_team": result.away_team,
                "match_date": as_of,
            },
        )

        breakdown = result.specialist_agent_breakdown or {}
        baseline = {
            "first_goal_team": result.first_goal_team,
            "first_goal_time_range": result.first_goal_time_range,
            "display_estimated_first_goal_minute": result.display_estimated_first_goal_minute,
            "confidence_score": result.confidence_score,
            "match_first_goal_range_probs": breakdown.get("match_first_goal_range_probs") or {},
        }

        feat = features or {}
        hybrid = self.hybrid_engine.score(
            fixture_id=int(result.fixture_id),
            competition_key=result.competition_key,
            features=feat,
            baseline=baseline,
            survival=survival,
            data_quality_score=float(result.data_quality_score),
            reliability=self._reliability,
            tier_calibration=tier_cal,
            home_team=result.home_team,
            away_team=result.away_team,
            team_calibrator=team_cal,
            range_calibrator=range_cal,
            minute_calibrator=minute_cal,
        )
        range_probs = survival.get("range_probabilities") or baseline.get("match_first_goal_range_probs")
        return format_hybrid_confidence_api(hybrid, range_probs=range_probs)

    def compute_from_row(
        self,
        row: dict[str, Any],
        *,
        features: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if row.get("no_prediction_flag"):
            return None
        snapshot = _parse_snapshot(row.get("hybrid_confidence_snapshot"))
        if snapshot:
            return snapshot

        breakdown = row.get("specialist_agent_breakdown")
        if isinstance(breakdown, str):
            try:
                breakdown = json.loads(breakdown)
            except json.JSONDecodeError:
                breakdown = {}
        breakdown = breakdown or {}

        match_date = row.get("match_date")
        result = GoalTimingPredictionResult(
            fixture_id=int(row["fixture_id"]),
            competition_key=str(row.get("competition_key") or "premier_league"),
            home_team=str(row.get("home_team") or "Home"),
            away_team=str(row.get("away_team") or "Away"),
            match_date=match_date if isinstance(match_date, datetime) else None,
            first_goal_team=row.get("first_goal_team") or "none",
            first_goal_time_range=str(row.get("first_goal_time_range") or "0-15"),
            display_estimated_first_goal_minute=row.get("display_estimated_first_goal_minute"),
            bucket_representative_minute=row.get("bucket_representative_minute"),
            weighted_average_minute=row.get("weighted_average_minute"),
            model_confidence_score=float(row.get("model_confidence_score") or 0),
            home_team_goal_probability_by_range=row.get("home_team_goal_probability_by_range") or {},
            away_team_goal_probability_by_range=row.get("away_team_goal_probability_by_range") or {},
            no_goal_before_minute_probability=row.get("no_goal_before_minute_probability") or {},
            confidence_score=float(row.get("confidence_score") or 0),
            data_quality_score=float(row.get("data_quality_score") or 0),
            explanation=str(row.get("explanation") or ""),
            specialist_agent_breakdown=breakdown,
            model_version=str(row.get("model_version") or ""),
            no_prediction_flag=bool(row.get("no_prediction_flag")),
            no_bet_flag=bool(row.get("no_bet_flag")),
        )
        return self.compute_snapshot(
            result,
            features=features,
            context={
                "home_team": result.home_team,
                "away_team": result.away_team,
                "match_date": result.match_date,
            },
        )

    @staticmethod
    def enrich_payload(payload: dict[str, Any], *, row: dict[str, Any] | None = None) -> dict[str, Any]:
        """Add hybrid_confidence to an API pick dict if missing."""
        if payload.get("hybrid_confidence"):
            return payload
        source = row or payload
        snap = _parse_snapshot(source.get("hybrid_confidence_snapshot"))
        if snap:
            payload["hybrid_confidence"] = snap
            return payload
        svc = HybridConfidenceProductionService()
        computed = svc.compute_from_row(source)
        if computed:
            payload["hybrid_confidence"] = computed
        return payload
