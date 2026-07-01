#!/usr/bin/env python3
"""Part E — Validate manual owner exact score predictions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.owner_manual_exact.constants import ARTIFACTS_DIR, DEFAULT_TIMEZONE, FINAL_REPORT
from worldcup_predictor.owner_manual_exact.resolver import _date_tag
from worldcup_predictor.owner_manual_exact.validation import validate_manual_predictions, write_final_report
from worldcup_predictor.owner_predict_eval.dates import resolve_process_date
from worldcup_predictor.owner_predict_eval.db_helpers import table_exists
from worldcup_predictor.research.wde_shadow_historical.helpers import table_count
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _production_counts() -> dict[str, int]:
    conn = connect_readonly(get_settings().sqlite_path)
    counts = {
        "worldcup_stored_predictions": table_count(conn, "worldcup_stored_predictions")
        if table_exists(conn, "worldcup_stored_predictions")
        else 0,
        "odds_snapshots": table_count(conn, "odds_snapshots") if table_exists(conn, "odds_snapshots") else 0,
        "ecse_prediction_snapshots": table_count(conn, "ecse_prediction_snapshots")
        if table_exists(conn, "ecse_prediction_snapshots")
        else 0,
    }
    conn.close()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="today")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    args = parser.parse_args()

    process_date = resolve_process_date(args.date, args.timezone)
    json_path = ARTIFACTS_DIR / f"manual_owner_exact_score_predictions_{_date_tag(process_date)}.json"
    if not json_path.exists():
        print(json.dumps({"error": f"missing {json_path}"}, indent=2))
        return 1

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["json_path"] = str(json_path)
    payload["md_path"] = str(
        Path("reports/owner") / f"manual_owner_exact_score_predictions_{_date_tag(process_date)}.md"
    )

    resolution_path = ARTIFACTS_DIR / f"manual_owner_match_resolution_{_date_tag(process_date)}.json"
    resolution = json.loads(resolution_path.read_text(encoding="utf-8")) if resolution_path.exists() else None

    production_before = _production_counts()
    validation = validate_manual_predictions(
        payload, production_before=production_before, resolution=resolution, process_date=process_date
    )
    write_final_report(payload, validation, process_date=process_date, resolution=resolution)

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
    print(f"Written: {FINAL_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
