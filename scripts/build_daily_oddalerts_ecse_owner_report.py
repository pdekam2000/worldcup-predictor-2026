#!/usr/bin/env python3
"""Build daily OddAlerts ECSE owner report from pipeline state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner.daily_oddalerts_ecse_owner_report import build_daily_oddalerts_ecse_owner_report
from worldcup_predictor.owner.daily_oddalerts_ecse_pipeline import DailyPipelineResult, state_artifact_path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-07-01")
    args = parser.parse_args()

    state_path = state_artifact_path(args.date)
    if not state_path.exists():
        print(f"Missing state: {state_path}", file=sys.stderr)
        return 2

    data = json.loads(state_path.read_text(encoding="utf-8"))
    result = DailyPipelineResult(
        run_id=data["run_id"],
        process_date=data["date"],
        date_from=data["date_from"],
        date_to=data["date_to"],
        window_days=data["window_days"],
        gmail={
            "emails_found": data.get("gmail_emails_scanned"),
            "files_downloaded": data.get("files_downloaded"),
            "duplicates_skipped": data.get("duplicates_skipped"),
        },
        import_summary={"probability_staged": data.get("rows_imported", 0)},
        ready_full_before=data.get("ready_full_before", 0),
        ready_full_after=data.get("ready_full_after", 0),
        promotion={
            "inserted_count": data.get("odds_snapshots_inserted"),
            "enriched_count": data.get("odds_snapshots_enriched"),
            "skipped_count": data.get("odds_snapshots_skipped"),
        },
        monitor={
            "discovered_count": data.get("monitor_candidates_discovered"),
            "written_count": data.get("monitor_records_written"),
            "skipped_ineligible_count": data.get("monitor_records_skipped_non_eligible"),
        },
        evaluation={"evaluated_count": data.get("evaluated_records")},
        skipped_reasons=data.get("skipped_reasons", {}),
        production_guard=data.get("production_guard", {}),
        final_recommendation=data.get("final_recommendation", ""),
    )
    out = build_daily_oddalerts_ecse_owner_report(result)
    print(json.dumps({"written": out["json"], "markdown": out["markdown"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
