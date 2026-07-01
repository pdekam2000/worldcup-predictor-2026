#!/usr/bin/env python3
"""PHASE WDE-RETRAIN-SHADOW-2 Part A — time-based train/val/test split."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.wde_shadow_historical.constants import SPLIT_ARTIFACT, TRAIN_PARQUET
from worldcup_predictor.research.wde_shadow_historical.split import load_dataset, split_time_based

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    df = load_dataset()
    split = split_time_based(df)
    print(
        json.dumps(
            {
                "total_rows": split.get("total_rows"),
                "train": split.get("train", {}).get("count"),
                "validation": split.get("validation", {}).get("count"),
                "test": split.get("test", {}).get("count"),
                "verification": split.get("verification"),
                "leakage_check": split.get("leakage_check"),
            },
            indent=2,
        )
    )
    print(f"Written: {SPLIT_ARTIFACT}")
    print(f"Written: {TRAIN_PARQUET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
