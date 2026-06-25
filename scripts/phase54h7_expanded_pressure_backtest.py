#!/usr/bin/env python3
"""Phase 54H-7 expanded pressure shadow backtest orchestrator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h7_expanded_pressure_backtest"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 54H-7 expanded pressure backtest")
    parser.add_argument("--skip-run", action="store_true")
    args = parser.parse_args()

    from worldcup_predictor.egie.pressure_backtest.pressure_expanded_runner import PressureExpandedRunner
    from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository

    repo = SportmonksPressureRepository()
    audit = repo.audit_coverage()
    fixture_count = int((audit.get("records") or {}).get("fixture_count") or 0)
    print(f"Pressure fixtures in store: {fixture_count}")

    if fixture_count < 100:
        print("WARNING: fixture count below expanded threshold; results may be insufficient")

    if args.skip_run and (ARTIFACT_DIR / "expanded_backtest_results.json").is_file():
        result = json.loads((ARTIFACT_DIR / "expanded_backtest_results.json").read_text(encoding="utf-8"))
    else:
        print("Running expanded pressure backtest pipeline...")
        result = PressureExpandedRunner().run()

    print(f"Leakage: {result.get('leakage_audit', {}).get('status')}")
    print(f"Proxy risk: {result.get('minute_proxy_audit', {}).get('proxy_risk_verdict')}")
    print(f"Recommendation: {result.get('recommendation')}")
    print(f"Artifacts: {ARTIFACT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
