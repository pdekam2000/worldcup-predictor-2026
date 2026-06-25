#!/usr/bin/env python3
"""Phase 52D — Hybrid confidence shadow replay + hold-out validation."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 52D hybrid confidence engine")
    parser.add_argument("--skip-shadow", action="store_true", help="Skip shadow replay")
    parser.add_argument("--limit", type=int, default=0, help="Limit fixtures (0=all)")
    args = parser.parse_args()

    from worldcup_predictor.egie.confidence.shadow_runner import HybridConfidenceShadowRunner
    from worldcup_predictor.egie.confidence.validation_runner import HybridConfidenceValidationRunner
    from worldcup_predictor.egie.survival.config import SHADOW_PREDICTIONS_PATH

    if not args.skip_shadow:
        runner = HybridConfidenceShadowRunner()
        records = runner.run_from_survival_jsonl(source_path=SHADOW_PREDICTIONS_PATH, persist=True)
        if args.limit:
            records = records[: args.limit]
        print(f"Hybrid shadow records written: {len(records)}")

    val = HybridConfidenceValidationRunner()
    payload = val.run(persist_artifact=True)
    print(json.dumps(
        {
            "phase_52d_status": payload.get("phase_52d_status"),
            "deploy_allowed": payload.get("deploy_allowed"),
            "monotonicity": payload.get("monotonicity"),
            "distribution": payload.get("distribution"),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
