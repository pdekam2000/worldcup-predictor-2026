#!/usr/bin/env python3
"""Phase B — sync upcoming Premier League fixtures for Goal Timing picks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

from worldcup_predictor.egie.ingest.targeted_upcoming_fixtures import run_targeted_upcoming_fixture_sync


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase B upcoming PL fixture sync")
    parser.add_argument("--max-api-calls", type=int, default=10, help="API budget cap (default 10)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = run_targeted_upcoming_fixture_sync(max_api_calls=int(args.max_api_calls))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0 if report.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
