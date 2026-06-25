#!/usr/bin/env python3
"""Phase 58C — Elite Orchestrator shadow runtime CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.elite_orchestrator.shadow_runner import run_shadow_runtime


def main() -> int:
    parser = argparse.ArgumentParser(description="Elite Orchestrator shadow runtime (58C)")
    parser.add_argument("--league-id", type=int, default=None, help="Filter by Sportmonks league_id (e.g. 732 WC)")
    parser.add_argument("--days-ahead", type=int, default=7, help="Horizon for upcoming fixtures")
    parser.add_argument("--limit", type=int, default=50, help="Max fixtures to process")
    parser.add_argument("--dry-run", action="store_true", help="Select fixtures and generate without writing")
    parser.add_argument("--force", action="store_true", help="Regenerate even if duplicate exists for today")
    args = parser.parse_args()

    report = run_shadow_runtime(
        days_ahead=args.days_ahead,
        limit=args.limit,
        league_id=args.league_id,
        dry_run=args.dry_run,
        force=args.force,
    )
    print(
        json.dumps(
            {
                "recommendation": report.get("recommendation"),
                "fixtures": report.get("fixtures_selected"),
                "predictions": report.get("predictions_generated"),
                "written": (report.get("write_result") or {}).get("written"),
                "dry_run": args.dry_run,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
