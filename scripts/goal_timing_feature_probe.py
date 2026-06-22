"""CLI — probe goal timing feature generation for one fixture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 51C goal timing feature probe")
    parser.add_argument("--fixture-id", type=int, required=True, help="Target fixture ID")
    parser.add_argument("--persist", action="store_true", help="Save features to goal_timing_features")
    parser.add_argument("--report-only", action="store_true", help="Coverage report only (no feature build)")
    parser.add_argument("--no-api", action="store_true", help="Disable API-Football fallback (stored data only)")
    parser.add_argument("--api-budget", type=int, default=0, help="Max API-Football event fetches (default 0)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text report")
    args = parser.parse_args(argv)

    from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
    from worldcup_predictor.goal_timing.service import GoalTimingFeatureService, format_probe_report

    if args.no_api or args.api_budget <= 0:
        service = GoalTimingFeatureService()
        budget = 0 if args.no_api else args.api_budget
        service.builder = GoalTimingFeatureBuilder(max_api_event_fetches=budget)
    else:
        service = GoalTimingFeatureService()
        service.builder = GoalTimingFeatureBuilder(max_api_event_fetches=args.api_budget)

    if args.report_only:
        payload = {"coverage": service.coverage_report(sample_fixture_id=args.fixture_id)}
    else:
        payload = service.probe_fixture_report(args.fixture_id, persist=args.persist)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        if args.report_only:
            print(json.dumps(payload["coverage"], indent=2, ensure_ascii=False))
        else:
            print(format_probe_report(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
