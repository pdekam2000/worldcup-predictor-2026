#!/usr/bin/env python3
"""Phase 54F-6B — full xG revalidation on 1,004 fixture dataset."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f6b_full_xg_revalidation"
DATASET = ROOT / "artifacts" / "phase54f6_expanded_dataset" / "expanded_egie_dataset.parquet"


def main() -> int:
    from worldcup_predictor.egie.xg_backtest.full_revalidation import FullXgRevalidationRunner

    if not DATASET.is_file():
        print(json.dumps({"error": f"dataset_missing:{DATASET}"}))
        return 1

    result = FullXgRevalidationRunner(DATASET).save(ARTIFACT_DIR)
    print(json.dumps(
        {
            "usable_fixtures": result["dataset_verification"]["usable_fixtures"],
            "test_fixtures": result["dataset_verification"]["test_fixtures"],
            "final_value_tier": result["final_value_tier"],
            "final_recommendation": result["final_recommendation"],
            "markets": {
                k: {
                    "delta_accuracy": v.get("delta", {}).get("accuracy"),
                    "bootstrap_significant": (v.get("statistics") or {}).get("bootstrap", {}).get("statistically_significant"),
                    "recommendation": v.get("recommendation"),
                }
                for k, v in result.get("markets", {}).items()
            },
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
