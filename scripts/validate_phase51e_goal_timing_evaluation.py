"""Phase 51E — goal timing evaluation pipeline validation."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_51E_GOAL_TIMING_EVALUATION_PIPELINE.md"


def main() -> int:
    checks: list[tuple[str, bool]] = []

    from worldcup_predictor.goal_timing.evaluation import evaluate_goal_timing_prediction
    from worldcup_predictor.goal_timing.learning_stats import _aggregate_statuses, build_goal_timing_learning_stats
    from worldcup_predictor.goal_timing.outcome_adapter import build_evaluation_actuals
    from worldcup_predictor.goal_timing.storage.repository import GoalTimingRepository
    from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome

    team_eval = evaluate_goal_timing_prediction(
        fixture_id=1,
        prediction_id="test-pred",
        predicted_first_goal_team="home",
        predicted_first_goal_time_range="16-30",
        estimated_first_goal_minute=22.0,
        actual_first_goal_team="home",
        actual_first_goal_minute=24,
    )
    checks.append(("team_market_correct", team_eval.first_goal_team_status == "correct"))
    checks.append(("range_market_correct", team_eval.time_range_status == "correct"))
    checks.append(("minute_market_partial_or_correct", team_eval.minute_tolerance_status in {"correct", "partial"}))

    wrong_eval = evaluate_goal_timing_prediction(
        fixture_id=2,
        prediction_id="test-pred-2",
        predicted_first_goal_team="away",
        predicted_first_goal_time_range="0-15",
        estimated_first_goal_minute=8.0,
        actual_first_goal_team="home",
        actual_first_goal_minute=72,
    )
    checks.append(("team_market_wrong", wrong_eval.first_goal_team_status == "wrong"))
    checks.append(("range_market_wrong", wrong_eval.time_range_status == "wrong"))

    outcome = FixtureOutcome(
        is_finished=True,
        actual_result="draw",
        final_score="0-0",
        evaluated_at=None,
        fixture_status="FT",
        first_goal_team=None,
        goal_events=(),
    )
    actuals = build_evaluation_actuals(outcome, home_team="Arsenal", away_team="Chelsea")
    checks.append(("zero_zero_team_none", actuals["actual_first_goal_team"] == "none"))

    agg = _aggregate_statuses(["correct", "correct", "wrong", "pending", "partial"])
    checks.append(("aggregate_winrate", abs((agg["winrate"] or 0) - (2 / 3)) < 0.001))
    checks.append(("aggregate_soft_winrate", agg["soft_winrate"] == 0.75))

    repo = GoalTimingRepository()
    checks.append(("repository_save_evaluation_method", hasattr(repo, "save_evaluation")))
    checks.append(("repository_list_evaluations_joined", hasattr(repo, "list_evaluations_joined")))

    stats = build_goal_timing_learning_stats()
    checks.append(("learning_stats_shape", "by_market" in stats and "by_league" in stats))

    from worldcup_predictor.api.routes import goal_timing as gt_routes

    route_paths = {getattr(r, "path", "") for r in gt_routes.router.routes}
    checks.append(("route_history", "/goal-timing/history" in route_paths))
    checks.append(("route_accuracy", "/goal-timing/accuracy" in route_paths))
    checks.append(("route_performance", "/goal-timing/performance" in route_paths))
    checks.append(("route_evaluations_run", "/goal-timing/evaluations/run" in route_paths))

    checks.append(("report_exists", REPORT.is_file()))

    failed = [name for name, ok in checks if not ok]
    print("Phase 51E validation")
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    if failed:
        print(f"\n{len(failed)} check(s) failed.", file=sys.stderr)
        return 1

    print(f"\nAll {len(checks)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
