#!/usr/bin/env python3
"""Request OddAlerts ECSE complete-coverage CSV exports (owner/internal)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.data_import.oddalerts_csv_request import (  # noqa: E402
    QUEUE_PATH,
    SUBMITTED_PATH,
    build_ecse_complete_request_queue,
    load_request_plan,
    load_submitted_ids,
    submit_ecse_requests,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Queue/submit OddAlerts ECSE complete CSV requests")
    parser.add_argument("--dry-run", action="store_true", help="Build queue only; do not submit")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--pause-for-login", action="store_true")
    parser.add_argument("--max-requests", type=int, default=50)
    parser.add_argument("--probability-min", type=int, default=None)
    parser.add_argument("--probability-max", type=int, default=100)
    args = parser.parse_args()

    plan = load_request_plan()
    queue = build_ecse_complete_request_queue(
        plan,
        probability_min=args.probability_min,
        probability_max=args.probability_max,
    )
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Queue: {queue['request_count']} requests | range {queue['probability_range']}")
    print(f"Written: {QUEUE_PATH}")

    submitted_before = len(load_submitted_ids())
    stats = submit_ecse_requests(
        queue,
        plan,
        dry_run=args.dry_run,
        headed=args.headed,
        pause_for_login=args.pause_for_login,
        max_requests=args.max_requests,
    )
    submitted_after = len(load_submitted_ids())

    print(json.dumps({**stats, "submitted_total": submitted_after, "submitted_before": submitted_before}, indent=2))
    if SUBMITTED_PATH.exists():
        print(f"Submitted log: {SUBMITTED_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
