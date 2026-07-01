#!/usr/bin/env python3
"""PHASE WDE-RETRAIN-SHADOW-2 Part D — backtest shadow WDE vs baselines and current production."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.wde_shadow_historical.backtest import backtest_shadow_vs_current
from worldcup_predictor.research.wde_shadow_historical.constants import BACKTEST_ARTIFACT, METRICS_ARTIFACT
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly
from worldcup_predictor.research.wde_shadow_historical.split import load_split_dataframes

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", default=None)
    args = parser.parse_args()

    train_df, val_df, test_df = load_split_dataframes()
    if test_df.empty:
        print(json.dumps({"status": "skipped", "reason": "empty_test_set"}, indent=2))
        return 0

    if args.model_dir:
        model_dir = Path(args.model_dir)
    elif METRICS_ARTIFACT.exists():
        metrics = json.loads(METRICS_ARTIFACT.read_text(encoding="utf-8"))
        model_dir = Path(metrics.get("model_dir", "models/shadow/wde_historical_csv_shadow_latest"))
    else:
        candidates = sorted(Path("models/shadow").glob("wde_historical_csv_shadow_*"))
        model_dir = candidates[-1] if candidates else Path("models/shadow/wde_historical_csv_shadow_latest")

    conn = connect_readonly(get_settings().sqlite_path)
    result = backtest_shadow_vs_current(conn, val_df, test_df, train_df, model_dir=model_dir)
    conn.close()

    print(json.dumps(result.get("comparison", {}), indent=2))
    print(f"Written: {BACKTEST_ARTIFACT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
