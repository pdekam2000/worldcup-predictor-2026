#!/usr/bin/env python3
"""One-shot OddAlerts lower-band Gmail watch + import + readiness pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.data_import.oddalerts_lower_band_pipeline import (  # noqa: E402
    REPORT_PATH,
    run_lower_band_watch_pipeline,
)
from worldcup_predictor.data_import.oddalerts_lower_band_watcher import (  # noqa: E402
    DEFAULT_CREDENTIALS,
    DEFAULT_TOKEN,
    INBOX_DIR,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Watch OddAlerts lower-band Gmail arrivals, import, validate, report"
    )
    parser.add_argument("--date", default="2026-06-30")
    parser.add_argument("--check-interval-minutes", type=int, default=10)
    parser.add_argument("--stable-rounds", type=int, default=2)
    parser.add_argument("--max-rounds", type=int, default=12)
    parser.add_argument("--inbox-dir", type=Path, default=INBOX_DIR)
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    parser.add_argument("--max-messages", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-watch",
        action="store_true",
        help="Reuse existing watch artifact; run import+validation only if stable",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    result = run_lower_band_watch_pipeline(
        process_date=args.date,
        check_interval_minutes=args.check_interval_minutes,
        stable_rounds=args.stable_rounds,
        max_rounds=args.max_rounds,
        inbox_dir=args.inbox_dir,
        credentials_path=args.credentials,
        token_path=args.token,
        max_messages=args.max_messages,
        dry_run=args.dry_run,
        skip_watch=args.skip_watch,
    )

    print(
        json.dumps(
            {
                "rounds_run": result.watch_artifact.get("rounds_run"),
                "stop_reason": result.watch_artifact.get("stop_reason"),
                "import_ran": result.import_ran,
                "new_files_total": result.watch_artifact.get("total_new_files_downloaded"),
                "probability_rows_before": result.baseline.probability_row_count,
                "probability_rows_after": result.after.probability_row_count,
                "ready_full_before": result.baseline.ready_full,
                "ready_full_after": result.after.ready_full,
                "ready_partial_before": result.baseline.ready_partial,
                "ready_partial_after": result.after.ready_partial,
                "final_recommendation": result.final_recommendation,
                "report": str(REPORT_PATH),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
