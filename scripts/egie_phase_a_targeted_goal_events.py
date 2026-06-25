#!/usr/bin/env python3
"""Phase A — targeted PL goal-event ingest (CLI)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

from worldcup_predictor.egie.ingest.targeted_goal_events import run_targeted_goal_event_ingest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase A targeted PL goal-event ingest")
    parser.add_argument("--max-api-calls", type=int, default=80, help="API budget cap (default 80)")
    parser.add_argument("--probe-fixture-id", type=int, default=1035553)
    parser.add_argument("--fixture-ids", type=str, default="", help="Comma-separated override list")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    fixture_ids = None
    if args.fixture_ids.strip():
        fixture_ids = [int(x.strip()) for x in args.fixture_ids.split(",") if x.strip()]

    report = run_targeted_goal_event_ingest(
        fixture_ids=fixture_ids,
        max_api_calls=int(args.max_api_calls),
        probe_fixture_id=int(args.probe_fixture_id),
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
