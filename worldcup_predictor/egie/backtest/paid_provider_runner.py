"""EGIE paid-provider strategy backtest (A–F) without modifying EliteGoalTimingEngine."""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.guards import backtest_mode
from worldcup_predictor.egie.provider_features.enrichment import (
    STRATEGY_LABELS,
    PaidProviderStrategy,
    enrich_agent_outputs,
)
from worldcup_predictor.egie.provider_features.models import ProviderFeatureVector
from worldcup_predictor.goal_timing.agents.orchestrator import GoalTimingAgentOrchestrator
from worldcup_predictor.goal_timing.backtest.aggregator import aggregate_backtest_results, build_calibration_stats
from worldcup_predictor.goal_timing.calibration import GoalTimingCalibrator
from worldcup_predictor.goal_timing.confidence import GoalTimingConfidenceEngine
from worldcup_predictor.goal_timing.config import MIN_DATA_QUALITY_FOR_PREDICTION
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.evaluation import evaluate_goal_timing_prediction
from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
from worldcup_predictor.goal_timing.leagues import is_goal_timing_prediction_league
from worldcup_predictor.goal_timing.models_stat.baseline import GoalTimingBaselineModel
from worldcup_predictor.goal_timing.outcome_adapter import build_evaluation_actuals

logger = logging.getLogger(__name__)

STRATEGIES: tuple[PaidProviderStrategy, ...] = ("A", "B", "C", "D", "E", "F")


class PaidProviderEgieBacktestRunner:
    """Compare EGIE baseline vs paid-provider enrichment strategies."""

    def __init__(self, *, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.stored = StoredGoalTimingAdapter(self.settings)
        self.feature_builder = GoalTimingFeatureBuilder(stored=self.stored, max_api_event_fetches=0)
        self.agents = GoalTimingAgentOrchestrator()
        self.baseline = GoalTimingBaselineModel()
        self.calibrator = GoalTimingCalibrator()
        self.confidence_engine = GoalTimingConfidenceEngine()
        self.resolver = FixtureOutcomeResolver(self.settings)

    def _predict_with_strategy(
        self,
        *,
        fixture_id: int,
        features: dict[str, Any],
        competition_key: str,
        context: dict[str, Any],
        strategy: PaidProviderStrategy,
    ) -> dict[str, Any]:
        feat = copy.deepcopy(features)
        feat["paid_provider_strategy"] = strategy
        agent_outputs = self.agents.run(fixture_id, features=feat, context=context)
        pf_raw = feat.get("provider_features")
        pf = ProviderFeatureVector(**pf_raw) if isinstance(pf_raw, dict) else None
        if strategy != "A" and pf:
            agent_outputs = enrich_agent_outputs(agent_outputs, pf, strategy)
        raw = self.baseline.predict(feat, agent_outputs)
        calibrated = self.calibrator.calibrate(raw)
        confidence, data_quality, model_confidence = self.confidence_engine.score(
            feat, agent_outputs, calibrated
        )
        league_ok = is_goal_timing_prediction_league(competition_key)
        no_prediction = (not league_ok) or data_quality < MIN_DATA_QUALITY_FOR_PREDICTION
        return {
            "no_prediction_flag": no_prediction,
            "data_quality_score": data_quality,
            "confidence_score": confidence,
            "model_confidence_score": model_confidence,
            "first_goal_team": calibrated.get("first_goal_team"),
            "first_goal_time_range": calibrated.get("first_goal_time_range"),
            "display_estimated_first_goal_minute": calibrated.get("display_estimated_first_goal_minute"),
            "provider_coverage": (pf.coverage if pf else {}),
        }

    def _coverage_for_strategy(self, pf: ProviderFeatureVector, strategy: PaidProviderStrategy) -> bool:
        cov = pf.coverage or {}
        if strategy == "B":
            return bool(cov.get("xg"))
        if strategy == "C":
            return bool(cov.get("pressure"))
        if strategy == "D":
            return bool(cov.get("odds"))
        if strategy == "E":
            return bool(cov.get("xg") or cov.get("pressure") or cov.get("odds"))
        if strategy == "F":
            return bool(any(cov.values()))
        return False

    def run(
        self,
        *,
        competition_key: str = "premier_league",
        limit: int | None = 200,
        strategies: tuple[PaidProviderStrategy, ...] = STRATEGIES,
    ) -> dict[str, Any]:
        before = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        fixtures = list(
            reversed(
                self.stored.repo.list_finished_fixtures_before(
                    before_kickoff=before,
                    competition_keys=[competition_key],
                    limit=limit,
                )
            )
        )

        per_strategy_rows: dict[str, list[dict[str, Any]]] = {s: [] for s in strategies}
        coverage_counts: dict[str, dict[str, int]] = {
            s: {"eligible": 0, "with_paid_data": 0} for s in strategies
        }

        with backtest_mode():
            for row in fixtures:
                fixture_id = int(row["fixture_id"])
                home_team = str(row.get("home_team") or "")
                away_team = str(row.get("away_team") or "")
                kickoff = str(row.get("kickoff_utc") or "")
                try:
                    outcome = self.resolver.resolve(fixture_id)
                    if not outcome.is_finished:
                        continue
                    actuals = build_evaluation_actuals(
                        outcome, home_team=home_team, away_team=away_team
                    )
                    evaluable = (
                        actuals["actual_first_goal_team"] is not None
                        or actuals["actual_first_goal_minute"] is not None
                        or str(actuals.get("final_score") or "").strip() in {"0-0", "0:0"}
                    )
                    if not evaluable:
                        continue

                    kickoff_dt = self.stored.parse_kickoff(kickoff)
                    ctx = {"home_team": home_team, "away_team": away_team, "match_date": kickoff_dt}
                    features = self.feature_builder.build(
                        fixture_id,
                        competition_key=competition_key,
                        as_of=kickoff_dt,
                        context=ctx,
                    )
                    pf_raw = features.get("provider_features")
                    pf = ProviderFeatureVector(**pf_raw) if isinstance(pf_raw, dict) else None

                    for strategy in strategies:
                        coverage_counts[strategy]["eligible"] += 1
                        if pf and self._coverage_for_strategy(pf, strategy):
                            coverage_counts[strategy]["with_paid_data"] += 1
                        pred = self._predict_with_strategy(
                            fixture_id=fixture_id,
                            features=features,
                            competition_key=competition_key,
                            context=ctx,
                            strategy=strategy,
                        )
                        if pred.get("no_prediction_flag"):
                            per_strategy_rows[strategy].append(
                                {
                                    "fixture_id": fixture_id,
                                    "no_prediction_flag": True,
                                    "evaluable": evaluable,
                                }
                            )
                            continue
                        evaluation = evaluate_goal_timing_prediction(
                            fixture_id=fixture_id,
                            prediction_id=f"paid-{strategy}-{fixture_id}",
                            predicted_first_goal_team=pred.get("first_goal_team"),
                            predicted_first_goal_time_range=pred.get("first_goal_time_range"),
                            estimated_first_goal_minute=pred.get("display_estimated_first_goal_minute"),
                            actual_first_goal_team=actuals["actual_first_goal_team"],
                            actual_first_goal_minute=actuals["actual_first_goal_minute"],
                        )
                        per_strategy_rows[strategy].append(
                            {
                                "fixture_id": fixture_id,
                                "strategy": strategy,
                                "no_prediction_flag": False,
                                "evaluable": evaluable,
                                "data_quality_score": pred.get("data_quality_score"),
                                "confidence_score": pred.get("confidence_score"),
                                "first_goal_team_status": evaluation.first_goal_team_status,
                                "time_range_status": evaluation.time_range_status,
                                "minute_tolerance_status": evaluation.minute_tolerance_status,
                                "provider_coverage": pred.get("provider_coverage"),
                            }
                        )
                except Exception as exc:
                    logger.exception("Paid provider backtest failed fixture_id=%s", fixture_id)
                    for strategy in strategies:
                        per_strategy_rows[strategy].append(
                            {"fixture_id": fixture_id, "error": str(exc)}
                        )

        summary: dict[str, Any] = {}
        for strategy in strategies:
            rows = per_strategy_rows[strategy]
            metrics = aggregate_backtest_results(rows)
            calibration = build_calibration_stats(rows)
            team_hit = (metrics.get("by_market") or {}).get("first_goal_team") or {}
            range_hit = (metrics.get("by_market") or {}).get("goal_range") or {}
            minute_hit = (metrics.get("by_market") or {}).get("goal_minute") or {}
            summary[strategy] = {
                "label": STRATEGY_LABELS.get(strategy, strategy),
                "coverage": coverage_counts[strategy],
                "metrics": metrics,
                "calibration": calibration,
                "first_goal_team_hit_rate": team_hit.get("winrate"),
                "goal_range_hit_rate": range_hit.get("winrate"),
                "goal_minute_soft_hit_rate": minute_hit.get("soft_winrate"),
            }

        baseline_hit = summary.get("A", {}).get("first_goal_team_hit_rate")
        recommendations = []
        for strategy in strategies:
            if strategy == "A":
                continue
            hit = summary.get(strategy, {}).get("first_goal_team_hit_rate")
            if hit is not None and baseline_hit is not None and hit > baseline_hit + 0.01:
                recommendations.append(f"Strategy {strategy} improves first_goal_team vs baseline")

        return {
            "status": "completed",
            "competition_key": competition_key,
            "fixtures_scanned": len(fixtures),
            "strategies": summary,
            "production_promotion_safe": len(recommendations) == 0,
            "promotion_notes": recommendations or ["No strategy beat baseline by >1pp — keep production unchanged."],
            "per_strategy_results": per_strategy_rows,
        }
