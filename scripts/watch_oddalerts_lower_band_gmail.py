#!/usr/bin/env python3
"""Watch Gmail for arriving OddAlerts lower-band CSV exports (owner/internal)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.data_import.oddalerts_lower_band_watcher import (  # noqa: E402
    DEFAULT_CREDENTIALS,
    DEFAULT_TOKEN,
    INBOX_DIR,
    run_lower_band_watch,
    watch_artifact_path,
    watch_final_recommendation,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch OddAlerts lower-band Gmail CSV arrivals")
    parser.add_argument("--date", default="2026-06-30")
    parser.add_argument("--tag", default="ecse-lower-band", help="Coverage tag label (informational)")
    parser.add_argument("--check-interval-minutes", type=int, default=10)
    parser.add_argument("--stable-rounds", type=int, default=2)
    parser.add_argument("--max-rounds", type=int, default=12)
    parser.add_argument("--inbox-dir", type=Path, default=INBOX_DIR)
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    parser.add_argument("--max-messages", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    artifact = run_lower_band_watch(
        process_date=args.date,
        check_interval_minutes=args.check_interval_minutes,
        stable_rounds=args.stable_rounds,
        max_rounds=args.max_rounds,
        inbox_dir=args.inbox_dir,
        credentials_path=args.credentials,
        token_path=args.token,
        max_messages=args.max_messages,
        dry_run=args.dry_run,
    )
    recommendation = watch_final_recommendation(artifact)
    artifact["final_recommendation"] = recommendation
    out_path = watch_artifact_path(args.date)
    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        json.dumps(
            {
                "rounds_run": artifact["rounds_run"],
                "stop_reason": artifact["stop_reason"],
                "total_new_files_downloaded": artifact["total_new_files_downloaded"],
                "total_duplicates_skipped": artifact["total_duplicates_skipped"],
                "recommendation": recommendation,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"Written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
