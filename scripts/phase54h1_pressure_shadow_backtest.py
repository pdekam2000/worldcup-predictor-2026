#!/usr/bin/env python3
"""Phase 54H-1 pressure shadow backtest orchestrator (backtest-only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h1_pressure_shadow_backtest"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 54H-1 pressure shadow backtest")
    parser.add_argument("--skip-dataset", action="store_true")
    parser.add_argument("--skip-backtest", action="store_true")
    parser.add_argument("--skip-audit", action="store_true")
    args = parser.parse_args()

    from worldcup_predictor.egie.pressure_backtest.pressure_dataset_builder import PressureDatasetBuilder
    from worldcup_predictor.egie.pressure_backtest.pressure_backtest_runner import PressureBacktestRunner
    from worldcup_predictor.egie.pressure_backtest.pressure_leakage_audit import run_pressure_leakage_audit

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    summary = {}
    if not args.skip_dataset:
        print("Building pressure datasets...")
        summary = PressureDatasetBuilder().save(ARTIFACT_DIR)
        print(json.dumps(summary, indent=2))

    audit = {}
    if not args.skip_audit:
        print("Running leakage audit...")
        audit = run_pressure_leakage_audit()
        print(f"Leakage audit: {audit.get('status')}")

    if not args.skip_backtest:
        print("Running backtest...")
        result = PressureBacktestRunner().run()
        print(f"Recommendation: {result.get('recommendation')}")

    print(f"Artifacts: {ARTIFACT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
