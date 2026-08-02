#!/usr/bin/env python3
"""Run PREDICTION_ENGINE_75 Phase 3 specialists + meta (research-only)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.prediction_engine_75.phase3 import run_phase3


def main() -> int:
    v = run_phase3()
    print(v.get("status"))
    for k in (
        "artifact_dir",
        "usable_n_excl_sealed",
        "priced_n",
        "specialists_fitted",
        "walk_forward_folds",
        "meta_walk_forward_mean_accuracy",
        "canonical_walk_forward_mean_accuracy",
        "locked_candidates",
        "primary_error_regimes",
        "sealed_holdout_status",
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
