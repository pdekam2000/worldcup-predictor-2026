"""STEP 6 — UEFA club A–F backtest (no EliteGoalTimingEngine changes)."""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.guards import backtest_mode
from worldcup_predictor.egie.provider_features.enrichment import STRATEGY_LABELS, PaidProviderStrategy, enrich_agent_outputs
from worldcup_predictor.egie.provider_features.models import ProviderFeatureVector
from worldcup_predictor.egie.uefa_club.feature_extractors import parse_match_result
from worldcup_predictor.egie.uefa_club.feature_store import UefaClubFeatureStore
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache
from worldcup_predictor.goal_timing.agents.orchestrator import GoalTimingAgentOrchestrator
from worldcup_predictor.goal_timing.backtest.aggregator import aggregate_backtest_results, build_calibration_stats
from worldcup_predictor.goal_timing.calibration import GoalTimingCalibrator
from worldcup_predictor.goal_timing.confidence import GoalTimingConfidenceEngine
from worldcup_predictor.goal_timing.config import MIN_DATA_QUALITY_FOR_PREDICTION
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.evaluation import evaluate_goal_timing_prediction
from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
from worldcup_predictor.goal_timing.models_stat.baseline import GoalTimingBaselineModel

logger = logging.getLogger(__name__)

STRATEGIES: tuple[PaidProviderStrategy, ...] = ("A", "B", "C", "D", "E", "F")


class UefaClubBacktestRunner:
    def __init__(self, *, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.stored = StoredGoalTimingAdapter(self.settings)
        self.feature_builder = GoalTimingFeatureBuilder(stored=self.stored, max_api_event_fetches=0)
        self.provider_store = UefaClubFeatureStore(self.settings)
        self.agents = GoalTimingAgentOrchestrator()
        self.baseline = GoalTimingBaselineModel()
        self.calibrator = GoalTimingCalibrator()
        self.confidence_engine = GoalTimingConfidenceEngine()

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

    def _predict(
        self,
        *,
        fixture_id: int,
        features: dict[str, Any],
        competition_key: str,
        context: dict[str, Any],
        strategy: PaidProviderStrategy,
        pf: ProviderFeatureVector | None,
    ) -> dict[str, Any]:
        feat = copy.deepcopy(features)
        feat["paid_provider_strategy"] = strategy
        if pf:
            feat["provider_features"] = pf.to_dict()
        agent_outputs = self.agents.run(fixture_id, features=feat, context=context)
        if strategy != "A" and pf:
            agent_outputs = enrich_agent_outputs(agent_outputs, pf, strategy)
        raw = self.baseline.predict(feat, agent_outputs)
        calibrated = self.calibrator.calibrate(raw)
        confidence, data_quality, model_confidence = self.confidence_engine.score(
            feat, agent_outputs, calibrated
        )
        no_prediction = data_quality < MIN_DATA_QUALITY_FOR_PREDICTION
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

    def run(
        self,
        fixtures: list[dict[str, Any]],
        *,
        strategies: tuple[PaidProviderStrategy, ...] = STRATEGIES,
    ) -> dict[str, Any]:
        per_strategy_rows: dict[str, list[dict[str, Any]]] = {s: [] for s in strategies}
        coverage_counts = {s: {"eligible": 0, "with_paid_data": 0} for s in strategies}

        with backtest_mode():
            for fx in fixtures:
                sm_id = int(fx.get("sportmonks_fixture_id") or 0)
                comp = str(fx.get("competition_key") or "champions_league")
                home = str(fx.get("home_team") or "")
                away = str(fx.get("away_team") or "")
                kickoff = str(fx.get("kickoff_utc") or "")
                try:
                    kickoff_dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).replace(tzinfo=None)
                except ValueError:
                    continue

                cache = load_cache(cache_path(self.settings, sm_id))
                payload = (cache or {}).get("payload")
                result = parse_match_result(payload, home_team=home, away_team=away)
                first_minute = result.get("first_goal_minute")
                first_team_side = result.get("first_goal_team_side")
                home_goals = int(result.get("home_goals") or 0)
                away_goals = int(result.get("away_goals") or 0)
                if first_minute is None and home_goals + away_goals == 0:
                    continue

                actuals = {
                    "actual_first_goal_team": first_team_side,
                    "actual_first_goal_minute": first_minute,
                    "final_score": f"{home_goals}-{away_goals}",
                }
                evaluable = first_team_side is not None or first_minute is not None

                ctx = {"home_team": home, "away_team": away, "match_date": kickoff_dt}
                features = self.feature_builder.build(
                    sm_id, competition_key=comp, as_of=kickoff_dt, context=ctx
                )
                pf = self.provider_store.build(sm_id, competition_key=comp, home_team=home, away_team=away)

                for strategy in strategies:
                    coverage_counts[strategy]["eligible"] += 1
                    if self._coverage_for_strategy(pf, strategy):
                        coverage_counts[strategy]["with_paid_data"] += 1
                    pred = self._predict(
                        fixture_id=sm_id,
                        features=features,
                        competition_key=comp,
                        context=ctx,
                        strategy=strategy,
                        pf=pf if strategy != "A" else None,
                    )
                    if pred.get("no_prediction_flag"):
                        per_strategy_rows[strategy].append(
                            {"fixture_id": sm_id, "no_prediction_flag": True, "evaluable": evaluable}
                        )
                        continue
                    evaluation = evaluate_goal_timing_prediction(
                        fixture_id=sm_id,
                        prediction_id=f"uefa-{strategy}-{sm_id}",
                        predicted_first_goal_team=pred.get("first_goal_team"),
                        predicted_first_goal_time_range=pred.get("first_goal_time_range"),
                        estimated_first_goal_minute=pred.get("display_estimated_first_goal_minute"),
                        actual_first_goal_team=actuals["actual_first_goal_team"],
                        actual_first_goal_minute=actuals["actual_first_goal_minute"],
                    )
                    per_strategy_rows[strategy].append(
                        {
                            "fixture_id": sm_id,
                            "strategy": strategy,
                            "competition_key": comp,
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

        best = max(
            strategies,
            key=lambda s: float(summary[s].get("first_goal_team_hit_rate") or 0),
        )
        baseline_rate = float(summary.get("A", {}).get("first_goal_team_hit_rate") or 0)
        best_rate = float(summary.get(best, {}).get("first_goal_team_hit_rate") or 0)
        promotion_safe = best != "A" and (best_rate - baseline_rate) >= 0.01

        return {
            "status": "completed",
            "fixtures_scanned": len(fixtures),
            "strategies": summary,
            "winning_strategy": best,
            "production_promotion_safe": promotion_safe,
            "per_strategy_results": per_strategy_rows,
        }
