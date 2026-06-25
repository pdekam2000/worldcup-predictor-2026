#!/usr/bin/env python3
"""Phase 51H — EGIE historical backtest validation."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "phase51h_egie_backtest.json"
REPORT = ROOT / "PHASE_51H_EGIE_HISTORICAL_BACKTEST_REPORT.md"


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.egie.guards import backtest_mode, external_api_allowed
    from worldcup_predictor.goal_timing.backtest.aggregator import aggregate_backtest_results, build_calibration_stats
    from worldcup_predictor.goal_timing.backtest.runner import GoalTimingBacktestRunner

    with backtest_mode():
        record("api_blocked_in_backtest", not external_api_allowed(operation="test"))

    engine_path = ROOT / "worldcup_predictor" / "goal_timing" / "engine.py"
    engine_src = engine_path.read_text(encoding="utf-8") if engine_path.is_file() else ""
    record("engine_unmodified_threshold", "MIN_DATA_QUALITY_FOR_PREDICTION" in engine_src)

    runner = GoalTimingBacktestRunner(lookback_days=730)
    payload = runner.run(competition_key="premier_league", limit=100)
    record("backtest_completes", payload.get("status") == "completed")
    record("db_only_policy", payload.get("data_policy", "").startswith("db_only"))

    metrics = payload.get("metrics") or {}
    record("has_by_market", "by_market" in metrics)
    record("has_by_league", "by_league" in metrics)
    record("has_dq_buckets", "by_dq_bucket" in metrics)
    record("has_conf_buckets", "by_confidence_bucket" in metrics)
    record("has_calibration", bool(payload.get("calibration")))

    scanned = int(metrics.get("fixtures_scanned") or 0)
    record("fixtures_scanned_min", scanned >= 1, str(scanned))

    if scanned > 0:
        sample_rows = [
            r
            for r in (payload.get("results") or [])
            if not r.get("no_prediction_flag") and r.get("evaluable")
        ]
        agg = aggregate_backtest_results(sample_rows)
        record("aggregator_matches_shape", "by_market" in agg)
        cal = build_calibration_stats(sample_rows)
        record("calibration_shape", "first_goal_team" in cal)

    if ARTIFACT.is_file():
        saved = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        record("artifact_exists", saved.get("phase") == "51H")
    else:
        record("artifact_exists", False, "run egie_phase51h_historical_backtest.py first")

    record("report_exists", REPORT.is_file())

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"Phase 51H validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
