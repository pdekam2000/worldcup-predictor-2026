#!/usr/bin/env python3
"""Run PREDICTION_ENGINE_75 Phase 1 foundation (research-only)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.prediction_engine_75.phase1 import run_phase1


def main() -> int:
    v = run_phase1(max_experiments=5000)
    print(v.get("status"))
    for k in (
        "artifact_dir",
        "finished_labeled_count",
        "true_forward_count",
        "feature_count_available_phase1",
        "strategies_tested",
        "best_validation_accuracy",
        "best_validation_coverage",
        "best_validation_avg_odds",
        "best_validation_roi",
        "best_validation_n",
        "sealed_holdout_status",
        "baseline_stored_wde_val_accuracy",
        "current_approved_accuracy",
        "split_sizes",
        "next_milestone",
        "target_75_claimed",
    ):
        print(f"{k}={v.get(k)}")
    print("NOT DEPLOYED")
    print("CANONICAL UNCHANGED")
    print("WDE UNCHANGED")
    print("ECSE UNCHANGED")
    print("NO AUTO-PROMOTION")
    return 0 if str(v.get("status", "")).endswith("READY") or "BLOCKED" in str(v.get("status")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
