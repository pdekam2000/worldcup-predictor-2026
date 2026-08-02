#!/usr/bin/env python3
"""Run PREDICTION_ENGINE_75 Phase 2 (research-only)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.prediction_engine_75.phase2 import run_phase2


def main() -> int:
    v = run_phase2(max_experiments=50000)
    print(v.get("status"))
    for k in (
        "artifact_dir",
        "phase1_usable_n",
        "phase2_usable_n",
        "cohort_counts",
        "priced_n_before",
        "priced_n_after",
        "features_before",
        "features_after",
        "walk_forward_fold_count",
        "walk_forward_mean_accuracy",
        "strategies_tested",
        "best_n25",
        "best_n50",
        "best_n100",
        "feature_families_helped",
        "feature_families_hurt",
        "primary_error_clusters",
        "sealed_holdout_status",
        "true_forward_status",
        "baseline_stored_wde_accuracy",
        "target_75_claimed",
    ):
        print(f"{k}={v.get(k)}")
    print("NOT DEPLOYED")
    print("CANONICAL UNCHANGED")
    print("WDE UNCHANGED")
    print("ECSE UNCHANGED")
    print("SEALED HOLDOUT UNOPENED")
    print("NO AUTO-PROMOTION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
