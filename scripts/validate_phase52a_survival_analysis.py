#!/usr/bin/env python3
"""Phase 52A — Survival analysis validation (shadow mode only)."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "phase52a_survival_results.json"
REPORT = ROOT / "PHASE_52A_SURVIVAL_ANALYSIS_REPORT.md"
BACKTEST_REPORT = ROOT / "PHASE_52A_SHADOW_BACKTEST_REPORT.md"
ENGINE_PATH = ROOT / "worldcup_predictor" / "goal_timing" / "engine.py"


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.egie.guards import backtest_mode, external_api_allowed
    from worldcup_predictor.egie.survival import (
        SurvivalBacktestRunner,
        SurvivalDatasetBuilder,
        SurvivalGoalTimingEngine,
        fit_kaplan_meier,
    )
    from worldcup_predictor.egie.survival.config import SURVIVAL_MODEL_VERSION

    # Module imports
    record("survival_package_imports", True)
    record("survival_model_version_set", bool(SURVIVAL_MODEL_VERSION))

    # KM sanity
    km = fit_kaplan_meier([(10.0, 1), (20.0, 1), (90.0, 0)])
    record("kaplan_meier_runs", km["n"] == 3 and len(km["survival_curve"]) >= 2)

    # No production engine rewrite
    engine_src = ENGINE_PATH.read_text(encoding="utf-8") if ENGINE_PATH.is_file() else ""
    record("production_engine_exists", "class EliteGoalTimingEngine" in engine_src)
    record("no_engine_replacement_marker", "SurvivalGoalTimingEngine" not in engine_src)

    with backtest_mode():
        record("api_blocked_in_backtest", not external_api_allowed(operation="phase52a_test"))
        runner = SurvivalBacktestRunner(lookback_days=730)
        payload = runner.run(competition_key="premier_league", limit=50, persist_shadow=False)

    record("backtest_completes", payload.get("status") == "completed")
    record("shadow_mode_only", payload.get("shadow_mode_only") is True)
    record("production_not_active", payload.get("production_active") is False)
    record("phase_52a_status", payload.get("phase_52a_status") == "SHADOW_BACKTEST_COMPLETE")
    record("has_comparison", bool(payload.get("comparison")))
    record("fixtures_compared_min", int(payload.get("fixtures_compared") or 0) >= 1)

    comp = payload.get("comparison") or {}
    record("comparison_has_range", "goal_range" in comp)
    record("comparison_has_minute_soft", "goal_minute_soft" in comp)

    # Dataset builder smoke
    builder = SurvivalDatasetBuilder()
    rows = builder.build_rows(competition_keys=["premier_league"], limit=20)
    record("dataset_builder_rows", len(rows) >= 1, str(len(rows)))

    # Shadow engine output shape
    if rows:
        engine = SurvivalGoalTimingEngine()
        with backtest_mode():
            pred = engine.predict_fixture(
                int(rows[0]["fixture_id"]),
                competition_key="premier_league",
            )
        record("survival_engine_range_probs", bool(pred.get("range_probabilities")))
        record("survival_engine_team_probs", bool(pred.get("team_probabilities")))
        record("survival_engine_shadow_flag", pred.get("shadow_mode") is True)

    record("deploy_not_justified_by_default", payload.get("deploy_justified") is False)

    if ARTIFACT.is_file():
        saved = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        record("artifact_exists", saved.get("phase") == "52A")
    else:
        record("artifact_exists", False, "run egie_phase52a_survival_backtest.py")

    record("analysis_report_exists", REPORT.is_file())
    record("backtest_report_exists", BACKTEST_REPORT.is_file())

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"Phase 52A validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
