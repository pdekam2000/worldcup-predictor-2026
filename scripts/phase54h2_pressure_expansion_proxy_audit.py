#!/usr/bin/env python3
"""Phase 54H-2 pressure coverage expansion + minute-proxy audit orchestrator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h2_pressure_expansion_proxy_audit"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 54H-2 pressure expansion + proxy audit")
    parser.add_argument("--skip-expansion", action="store_true")
    parser.add_argument("--skip-dataset", action="store_true")
    parser.add_argument("--skip-proxy-audit", action="store_true")
    parser.add_argument("--skip-revalidation", action="store_true")
    parser.add_argument("--max-calls", type=int, default=120)
    args = parser.parse_args()

    from worldcup_predictor.egie.pressure_backtest.pressure_dataset_builder import (
        ARTIFACT_DIR_H2,
        PressureDatasetBuilder,
    )
    from worldcup_predictor.egie.pressure_backtest.minute_proxy_audit import run_minute_proxy_audit
    from worldcup_predictor.egie.pressure_backtest.pressure_leakage_audit import run_pressure_leakage_audit
    from worldcup_predictor.egie.pressure_backtest.pressure_revalidation_runner import PressureRevalidationRunner
    from worldcup_predictor.feature_store.pressure_store.sportmonks_pressure_store import SportmonksPressureFeatureStore

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    expansion = {}
    if not args.skip_expansion:
        print("Expanding pressure coverage (cache-first, capped API)...")
        store = SportmonksPressureFeatureStore()
        expansion = store.backfill_expansion(max_calls=args.max_calls)
        (ARTIFACT_DIR / "coverage_expansion.json").write_text(
            json.dumps(expansion, indent=2, default=str), encoding="utf-8"
        )
        print(
            f"Coverage: {expansion.get('before_fixtures')} -> {expansion.get('after_fixtures')} "
            f"(target 150: {expansion.get('target_met_minimum')})"
        )

    summary = {}
    if not args.skip_dataset:
        print("Rebuilding pressure datasets...")
        summary = PressureDatasetBuilder().save(ARTIFACT_DIR_H2, phase="54H-2")
        print(json.dumps(summary, indent=2))

    print("Running leakage audit...")
    leak = run_pressure_leakage_audit(ARTIFACT_DIR_H2)
    print(f"Leakage: {leak.get('status')}")

    proxy = {}
    if not args.skip_proxy_audit:
        print("Running minute-proxy audit...")
        proxy = run_minute_proxy_audit()
        print(f"Proxy risk: {proxy.get('proxy_risk_verdict')}")

    if not args.skip_revalidation:
        print("Running revalidation...")
        result = PressureRevalidationRunner().run(proxy_audit=proxy)
        print(f"Recommendation: {result.get('recommendation')}")

    print(f"Artifacts: {ARTIFACT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
