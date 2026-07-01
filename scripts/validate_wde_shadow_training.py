#!/usr/bin/env python3
"""PHASE WDE-RETRAIN-SHADOW-2 Part E — validate shadow training gate and write report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.wde_shadow_historical.constants import (
    BACKTEST_ARTIFACT,
    DATASET_SUMMARY,
    METRICS_ARTIFACT,
    SPLIT_ARTIFACT,
    TRAINING_BACKTEST_REPORT,
    VALIDATION_ARTIFACT,
)
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count, table_exists
from worldcup_predictor.research.wde_shadow_historical.promotion_gate import validate_promotion_gate
from worldcup_predictor.research.wde_shadow_historical.training_backtest_report import write_training_backtest_report

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _production_counts() -> dict[str, int]:
    conn = connect_readonly(get_settings().sqlite_path)
    counts = {
        "worldcup_stored_predictions": table_count(conn, "worldcup_stored_predictions")
        if table_exists(conn, "worldcup_stored_predictions")
        else 0,
        "odds_snapshots": table_count(conn, "odds_snapshots") if table_exists(conn, "odds_snapshots") else 0,
    }
    conn.close()
    return counts


def main() -> int:
    production_before = _production_counts()
    split = _load(SPLIT_ARTIFACT)
    metrics = _load(METRICS_ARTIFACT)
    backtest = _load(BACKTEST_ARTIFACT)
    dataset_summary = _load(DATASET_SUMMARY)

    model_dir = Path(metrics.get("model_dir", "")) if metrics.get("model_dir") else None

    # Preliminary validation for recommendation (report not written yet)
    validation = validate_promotion_gate(
        split,
        metrics,
        backtest,
        model_dir=model_dir,
        production_before=production_before,
        require_report=False,
    )
    write_training_backtest_report(
        split=split,
        metrics=metrics,
        backtest=backtest,
        validation=validation,
        dataset_summary=dataset_summary,
    )
    # Re-check report exists
    if TRAINING_BACKTEST_REPORT.exists():
        validation["checks"].append({"check": "training_backtest_report", "passed": True, "detail": ""})
        validation["passed"] = sum(1 for c in validation["checks"] if c["passed"])
        validation["failed"] = sum(1 for c in validation["checks"] if not c["passed"])
        VALIDATION_ARTIFACT.write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        json.dumps(
            {
                "passed": validation["passed"],
                "failed": validation["failed"],
                "recommendation": validation["final_recommendation"],
            },
            indent=2,
        )
    )
    print(f"Written: {VALIDATION_ARTIFACT}")
    print(f"Written: {TRAINING_BACKTEST_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
