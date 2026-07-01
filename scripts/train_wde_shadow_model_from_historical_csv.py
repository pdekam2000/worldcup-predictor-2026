#!/usr/bin/env python3
"""PHASE WDE-RETRAIN-SHADOW-2 Part C — train shadow WDE tabular models."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.wde_shadow_historical.constants import METRICS_ARTIFACT, SHADOW_MODELS_DIR
from worldcup_predictor.research.wde_shadow_historical.split import load_split_dataframes
from worldcup_predictor.research.wde_shadow_historical.trainer import train_shadow_models

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Model tag YYYY-MM-DD")
    args = parser.parse_args()

    train_df, val_df, _ = load_split_dataframes()
    if train_df.empty:
        print(json.dumps({"status": "skipped", "reason": "empty_train_set"}, indent=2))
        return 0

    tag = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    model_dir = SHADOW_MODELS_DIR / f"wde_historical_csv_shadow_{tag.replace('-', '')}"

    metrics = train_shadow_models(train_df, val_df, model_dir=model_dir, process_date=tag)
    print(json.dumps(metrics, indent=2))
    print(f"Written: {METRICS_ARTIFACT}")
    print(f"Model dir: {model_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
