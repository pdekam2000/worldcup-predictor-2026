"""Phase API-K — UEFA odds sub-strategy backtest (A, D1–D8)."""

from __future__ import annotations

import copy
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.guards import backtest_mode
from worldcup_predictor.egie.uefa_club.feature_extractors import parse_match_result
from worldcup_predictor.egie.uefa_club.odds_enrichment import (
    coverage_for_odds_strategy,
    enrich_odds_substrategy,
)
from worldcup_predictor.egie.uefa_club.odds_intelligence import (
    ODDS_SUBSTRATEGY_LABELS,
    OddsSubStrategy,
    parse_uefa_odds_deep,
)
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

ODDS_STRATEGIES: tuple[OddsSubStrategy, ...] = ("A", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8")


class UefaOddsBacktestRunner:
    def __init__(self, *, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.stored = StoredGoalTimingAdapter(self.settings)
        self.feature_builder = GoalTimingFeatureBuilder(stored=self.stored, max_api_event_fetches=0)
        self.agents = GoalTimingAgentOrchestrator()
        self.baseline = GoalTimingBaselineModel()
        self.calibrator = GoalTimingCalibrator()
        self.confidence_engine = GoalTimingConfidenceEngine()

    def _predict(
        self,
        *,
        fixture_id: int,
        features: dict[str, Any],
        context: dict[str, Any],
        strategy: OddsSubStrategy,
        odds_features: dict[str, Any],
    ) -> dict[str, Any]:
        feat = copy.deepcopy(features)
        feat["paid_provider_strategy"] = "D" if strategy != "A" else "A"
        feat["has_reliable_goal_odds"] = strategy != "A" and coverage_for_odds_strategy(odds_features, strategy)
        feat["provider_features"] = {
            "odds_implied_home": odds_features.get("consensus_implied_home"),
            "odds_implied_away": odds_features.get("consensus_implied_away"),
            "odds_implied_draw": odds_features.get("consensus_implied_draw"),
            "odds_movement_home": odds_features.get("movement_home"),
        }
        agent_outputs = self.agents.run(fixture_id, features=feat, context=context)
        if strategy != "A":
            agent_outputs = enrich_odds_substrategy(agent_outputs, odds_features, strategy)
        raw = self.baseline.predict(feat, agent_outputs)
        calibrated = self.calibrator.calibrate(raw)
        confidence, data_quality, model_confidence = self.confidence_engine.score(feat, agent_outputs, calibrated)
        no_prediction = data_quality < MIN_DATA_QUALITY_FOR_PREDICTION
        return {
            "no_prediction_flag": no_prediction,
            "data_quality_score": data_quality,
            "confidence_score": confidence,
            "model_confidence_score": model_confidence,
            "first_goal_team": calibrated.get("first_goal_team"),
            "first_goal_time_range": calibrated.get("first_goal_time_range"),
            "display_estimated_first_goal_minute": calibrated.get("display_estimated_first_goal_minute"),
        }

    def run(self, fixtures: list[dict[str, Any]]) -> dict[str, Any]:
        per_strategy_rows: dict[str, list[dict[str, Any]]] = {s: [] for s in ODDS_STRATEGIES}
        coverage_counts = {s: {"eligible": 0, "with_odds_data": 0} for s in ODDS_STRATEGIES}

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

                odds_features = parse_uefa_odds_deep(payload)
                actuals = {
                    "actual_first_goal_team": first_team_side,
                    "actual_first_goal_minute": first_minute,
                    "final_score": f"{home_goals}-{away_goals}",
                }
                evaluable = first_team_side is not None or first_minute is not None
                ctx = {"home_team": home, "away_team": away, "match_date": kickoff_dt}
                features = self.feature_builder.build(sm_id, competition_key=comp, as_of=kickoff_dt, context=ctx)

                for strategy in ODDS_STRATEGIES:
                    coverage_counts[strategy]["eligible"] += 1
                    if coverage_for_odds_strategy(odds_features, strategy):
                        coverage_counts[strategy]["with_odds_data"] += 1
                    pred = self._predict(
                        fixture_id=sm_id,
                        features=features,
                        context=ctx,
                        strategy=strategy,
                        odds_features=odds_features,
                    )
                    if pred.get("no_prediction_flag"):
                        per_strategy_rows[strategy].append(
                            {"fixture_id": sm_id, "no_prediction_flag": True, "evaluable": evaluable}
                        )
                        continue
                    evaluation = evaluate_goal_timing_prediction(
                        fixture_id=sm_id,
                        prediction_id=f"uefa-odds-{strategy}-{sm_id}",
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
                        }
                    )

        summary: dict[str, Any] = {}
        for strategy in ODDS_STRATEGIES:
            rows = per_strategy_rows[strategy]
            metrics = aggregate_backtest_results(rows)
            calibration = build_calibration_stats(rows)
            team_hit = (metrics.get("by_market") or {}).get("first_goal_team") or {}
            range_hit = (metrics.get("by_market") or {}).get("goal_range") or {}
            minute_hit = (metrics.get("by_market") or {}).get("goal_minute") or {}
            summary[strategy] = {
                "label": ODDS_SUBSTRATEGY_LABELS.get(strategy, strategy),
                "coverage": coverage_counts[strategy],
                "metrics": metrics,
                "calibration": calibration,
                "first_goal_team_hit_rate": team_hit.get("winrate"),
                "goal_range_hit_rate": range_hit.get("winrate"),
                "goal_minute_soft_hit_rate": minute_hit.get("soft_winrate"),
                "fg_pending": team_hit.get("pending"),
                "fg_pending_rate": round(team_hit.get("pending", 0) / max(1, team_hit.get("total", 1)), 4),
            }

        return {
            "status": "completed",
            "fixtures_scanned": len(fixtures),
            "strategies": summary,
            "per_strategy_results": per_strategy_rows,
        }


def save_backtest(result: dict[str, Any], path: Path) -> None:
    slim = {k: v for k, v in result.items() if k != "per_strategy_results"}
    path.write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")
    path.with_name("uefa_odds_backtest_full.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
