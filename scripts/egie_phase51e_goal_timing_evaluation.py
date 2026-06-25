"""Phase 51E — run goal-timing evaluation learning loop."""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

from worldcup_predictor.goal_timing.evaluation_job import (
    run_goal_timing_evaluations,
    run_goal_timing_learning_loop,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="EGIE Phase 51E — goal timing evaluation loop")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--max-api-calls", type=int, default=50)
    parser.add_argument("--no-refresh", action="store_true", help="Skip API result refresh")
    parser.add_argument("--full", action="store_true", help="Include learning stats in output")
    args = parser.parse_args()

    if args.full:
        payload = run_goal_timing_learning_loop(
            limit=args.limit,
            max_api_calls=args.max_api_calls,
        )
    else:
        job = run_goal_timing_evaluations(
            limit=args.limit,
            refresh_first=not args.no_refresh,
            max_api_calls=args.max_api_calls,
        )
        payload = job.to_dict()

    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
