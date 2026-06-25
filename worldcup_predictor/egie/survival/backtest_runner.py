"""Historical backtest: baseline EGIE vs survival shadow layer."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.guards import backtest_mode
from worldcup_predictor.egie.survival.config import (
    BASELINE_REFERENCE,
    SUCCESS_CRITERIA,
    SURVIVAL_MODEL_VERSION,
)
from worldcup_predictor.egie.survival.shadow_runner import SurvivalShadowRunner
from worldcup_predictor.goal_timing.backtest.aggregator import aggregate_backtest_results, build_calibration_stats
from worldcup_predictor.goal_timing.backtest.runner import GoalTimingBacktestRunner
from worldcup_predictor.goal_timing.config import BACKTEST_DEFAULT_LOOKBACK_DAYS
from worldcup_predictor.goal_timing.outcome_adapter import build_evaluation_actuals

logger = logging.getLogger(__name__)


def _rows_from_shadow(shadow_records: list[dict[str, Any]], *, engine: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in shadow_records:
        pred = rec.get(engine) or {}
        ev = rec.get(f"{engine}_eval") or {}
        if pred.get("no_prediction_flag"):
            rows.append(
                {
                    "fixture_id": rec.get("fixture_id"),
                    "no_prediction_flag": True,
                    "evaluable": bool(rec.get("actuals")),
                    "data_quality_score": pred.get("data_quality_score"),
                    "confidence_score": pred.get("confidence_score"),
                }
            )
            continue
        rows.append(
            {
                "fixture_id": rec.get("fixture_id"),
                "competition_key": rec.get("competition_key"),
                "no_prediction_flag": False,
                "evaluable": bool(ev),
                "data_quality_score": pred.get("data_quality_score"),
                "confidence_score": pred.get("confidence_score"),
                "predicted_first_goal_team": pred.get("first_goal_team"),
                "predicted_first_goal_time_range": pred.get("first_goal_time_range"),
                "predicted_minute": pred.get("display_estimated_first_goal_minute"),
                "first_goal_team_status": ev.get("first_goal_team_status"),
                "time_range_status": ev.get("time_range_status"),
                "minute_tolerance_status": ev.get("minute_tolerance_status"),
            }
        )
    return rows


def _soft_winrate(metrics: dict[str, Any], market: str) -> float | None:
    m = (metrics.get("by_market") or {}).get(market) or {}
    correct = int(m.get("correct") or 0)
    partial = int(m.get("partial") or 0)
    wrong = int(m.get("wrong") or 0)
    denom = correct + partial + wrong
    return round((correct + partial) / denom, 4) if denom else None


class SurvivalBacktestRunner:
    """Replay fixtures and compare baseline vs survival (shadow only)."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        lookback_days: int = BACKTEST_DEFAULT_LOOKBACK_DAYS,
    ) -> None:
        self.settings = settings or get_settings()
        self.lookback_days = lookback_days
        self.baseline_runner = GoalTimingBacktestRunner(settings=self.settings, lookback_days=lookback_days)
        self.shadow = SurvivalShadowRunner()
        self.resolver = FixtureOutcomeResolver(self.settings)

    def run(
        self,
        *,
        competition_key: str = "premier_league",
        limit: int | None = None,
        require_goal_events: bool = True,
        persist_shadow: bool = False,
    ) -> dict[str, Any]:
        start = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        end = datetime.now(timezone.utc)
        shadow_records: list[dict[str, Any]] = []
        errors = 0

        with backtest_mode():
            fixtures = self.baseline_runner.list_candidate_fixtures(
                competition_key=competition_key,
                limit=limit,
            )
            for row in fixtures:
                fixture_id = int(row["fixture_id"])
                home_team = str(row.get("home_team") or "")
                away_team = str(row.get("away_team") or "")
                kickoff = str(row.get("kickoff_utc") or "")
                try:
                    outcome = self.resolver.resolve(fixture_id)
                    if not outcome.is_finished:
                        continue
                    event_count = self.baseline_runner.stored.repo.count_fixture_goal_events(fixture_id)
                    if require_goal_events and event_count == 0 and not row.get("first_goal_minute"):
                        continue
                    actuals = build_evaluation_actuals(
                        outcome,
                        home_team=home_team,
                        away_team=away_team,
                    )
                    if actuals["actual_first_goal_team"] is None and actuals["actual_first_goal_minute"] is None:
                        continue
                    kickoff_dt = self.baseline_runner.stored.parse_kickoff(kickoff)
                    rec = self.shadow.run_fixture(
                        fixture_id,
                        competition_key=competition_key,
                        as_of=kickoff_dt,
                        context={
                            "home_team": home_team,
                            "away_team": away_team,
                            "match_date": kickoff_dt,
                        },
                        actuals=actuals,
                        persist=persist_shadow,
                    )
                    shadow_records.append(rec)
                except Exception:
                    logger.exception("Survival backtest failed fixture_id=%s", fixture_id)
                    errors += 1

        baseline_rows = _rows_from_shadow(shadow_records, engine="baseline")
        survival_rows = _rows_from_shadow(shadow_records, engine="survival")
        baseline_metrics = aggregate_backtest_results(baseline_rows)
        survival_metrics = aggregate_backtest_results(survival_rows)
        baseline_cal = build_calibration_stats(baseline_rows)
        survival_cal = build_calibration_stats(survival_rows)

        def _market_wr(metrics: dict[str, Any], market: str) -> float | None:
            m = (metrics.get("by_market") or {}).get(market) or {}
            return m.get("winrate")

        comparison = {
            "first_goal_team": {
                "baseline": _market_wr(baseline_metrics, "first_goal_team"),
                "survival": _market_wr(survival_metrics, "first_goal_team"),
                "delta": None,
                "target_min": SUCCESS_CRITERIA["first_goal_team_winrate_min"],
            },
            "goal_range": {
                "baseline": _market_wr(baseline_metrics, "goal_range"),
                "survival": _market_wr(survival_metrics, "goal_range"),
                "delta": None,
                "target_min": SUCCESS_CRITERIA["goal_range_winrate_min"],
            },
            "goal_minute_exact": {
                "baseline": _market_wr(baseline_metrics, "goal_minute"),
                "survival": _market_wr(survival_metrics, "goal_minute"),
            },
            "goal_minute_soft": {
                "baseline": _soft_winrate(baseline_metrics, "goal_minute"),
                "survival": _soft_winrate(survival_metrics, "goal_minute"),
                "target_min": SUCCESS_CRITERIA["goal_minute_soft_winrate_min"],
            },
        }
        for key in ("first_goal_team", "goal_range"):
            b = comparison[key]["baseline"]
            s = comparison[key]["survival"]
            if b is not None and s is not None:
                comparison[key]["delta"] = round(s - b, 4)
        b_soft = comparison["goal_minute_soft"]["baseline"]
        s_soft = comparison["goal_minute_soft"]["survival"]
        if b_soft is not None and s_soft is not None:
            comparison["goal_minute_soft"]["delta"] = round(s_soft - b_soft, 4)

        meets_range = (comparison["goal_range"]["survival"] or 0) >= SUCCESS_CRITERIA["goal_range_winrate_min"]
        meets_minute = (comparison["goal_minute_soft"]["survival"] or 0) >= SUCCESS_CRITERIA[
            "goal_minute_soft_winrate_min"
        ]
        meets_team = (comparison["first_goal_team"]["survival"] or 0) >= SUCCESS_CRITERIA[
            "first_goal_team_winrate_min"
        ]
        deploy_justified = meets_range and meets_minute and meets_team

        return {
            "status": "completed",
            "phase": "52A",
            "phase_52a_status": "SHADOW_BACKTEST_COMPLETE",
            "production_active": False,
            "shadow_mode_only": True,
            "survival_model_version": SURVIVAL_MODEL_VERSION,
            "competition_key": competition_key,
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "errors": errors,
            "fixtures_compared": len(shadow_records),
            "baseline_reference_51h": BASELINE_REFERENCE,
            "success_criteria": SUCCESS_CRITERIA,
            "comparison": comparison,
            "deploy_justified": deploy_justified,
            "baseline_metrics": baseline_metrics,
            "survival_metrics": survival_metrics,
            "baseline_calibration": baseline_cal,
            "survival_calibration": survival_cal,
            "shadow_records": shadow_records,
        }
