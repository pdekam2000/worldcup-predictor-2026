#!/usr/bin/env python3
"""PHASE WC-OWNER-EVAL-SUMMARY — Build owner WC evaluation summary from existing sync data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner.wc_owner_eval_summary import REPORTS_DIR, build_wc_owner_eval_summary

DEFAULT_PRED = REPORTS_DIR / "wc_today_predictions_20260630.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Build WC owner evaluation summary")
    parser.add_argument(
        "--prediction-report",
        type=str,
        default=str(DEFAULT_PRED),
        help="Path to wc_today_predictions JSON",
    )
    parser.add_argument("--date-ymd", type=str, default=None, help="Override YYYYMMDD suffix")
    args = parser.parse_args()

    result = build_wc_owner_eval_summary(
        prediction_report_path=Path(args.prediction_report),
        date_ymd=args.date_ymd,
    )
    print(
        json.dumps(
            {
                "final_recommendation": result["final_recommendation"],
                "metrics": result["metrics"],
                "md_path": result["md_path"],
                "json_path": result["json_path"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
