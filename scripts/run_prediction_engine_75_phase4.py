#!/usr/bin/env python3
"""Run PREDICTION_ENGINE_75 Phase 4 locked holdout + true-forward readiness."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.prediction_engine_75.phase4 import run_phase4


def main() -> int:
    v = run_phase4()
    print(v.get("status"))
    for k in (
        "artifact_dir",
        "candidate_lock_status",
        "manifest_sha256",
        "holdout_integrity_status",
        "holdout_n",
        "locked_candidate_accuracy",
        "locked_candidate_coverage",
        "locked_candidate_roi",
        "holdout_verdicts",
        "best_holdout_candidate",
        "small_sample_warning",
        "true_forward_pipeline_readiness",
        "timers_prepared",
        "timers_enabled",
        "current_evaluated_true_forward_n",
        "gate_progress",
        "target_75_claimed",
    ):
        print(f"{k}={v.get(k)}")
    print("NOT DEPLOYED")
    print("CANONICAL UNCHANGED")
    print("WDE UNCHANGED")
    print("ECSE UNCHANGED")
    print("NO RETUNING AFTER HOLDOUT")
    print("NO AUTO-PROMOTION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
