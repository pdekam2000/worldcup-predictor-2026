"""CLI — EGIE Phase 1B API-Football Premier League raw ingest."""

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
    parser = argparse.ArgumentParser(description="EGIE Phase 1B — API-Football Premier League ingest")
    parser.add_argument("--season", type=int, default=None, help="Season year (default from manifest)")
    parser.add_argument(
        "--max-fixtures",
        type=int,
        default=None,
        help="Limit finished fixture detail fetches (dev/quota safe)",
    )
    parser.add_argument(
        "--fixtures-only",
        action="store_true",
        help="Ingest standings + fixture list only (skip per-fixture resources)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    args = parser.parse_args(argv)

    from worldcup_predictor.egie.ingest.api_football_premier_league import ApiFootballPremierLeagueIngestor

    ingestor = ApiFootballPremierLeagueIngestor()
    result = ingestor.run(
        season=args.season,
        max_fixtures=args.max_fixtures,
        include_fixture_details=not args.fixtures_only,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("\n=== EGIE Phase 1B — Premier League Ingest ===")
        print(f"Status: {result.status}")
        print(f"Run ID: {result.run_id}")
        print(f"Season: {result.season}")
        print(f"API calls (live): {result.api_calls_live}")
        print(f"Rows saved: {result.rows_saved}")
        print(f"Rows skipped (duplicate): {result.rows_skipped_duplicate}")
        print(f"Fixtures processed: {result.fixtures_processed}")
        print(f"Resource counts: {json.dumps(result.resource_counts, indent=2)}")
        if result.errors:
            print(f"Errors: {result.errors}")

    return 0 if result.status in {"completed", "completed_with_errors"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
