#!/usr/bin/env python3
"""Run MASSIVE_SEARCH_DATASET_RECOVERY_AND_TRUE_FORWARD_EXPANSION."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.massive_algorithm_search.dataset_recovery.rebuild import run_recovery


def main() -> int:
    v = run_recovery()
    print(json.dumps({k: v.get(k) for k in [
        "status",
        "final_valid_model_labeled_n",
        "final_priced_n",
        "newly_recovered_model_labeled_n",
        "scale_decision",
        "true_forward_collection_active",
        "artifact_dir",
    ]}, indent=2))
    return 0 if v.get("status") in {
        "MASSIVE_DATASET_RECOVERY_COMPLETE",
        "MASSIVE_DATASET_RECOVERY_PARTIAL",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
