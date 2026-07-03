#!/usr/bin/env python3
"""CLAUDE-OPS-1 — Read-only owner prediction inspection (no DB writes, no providers)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner.prediction_inspection import (  # noqa: E402
    DB_MISSING_MSG,
    InspectionConfig,
    format_predictions_output,
    inspect_owner_predictions,
    sanitize_for_output,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only owner prediction inspection")
    parser.add_argument("--date", default="today", help="today|tomorrow|yesterday|YYYY-MM-DD")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument(
        "--scope",
        default="all",
        choices=["stored", "evaluated", "pending", "all"],
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--format",
        default="table",
        choices=["table", "json", "markdown"],
        dest="output_format",
    )
    parser.add_argument(
        "--market",
        default="all",
        choices=["1x2", "btts", "over_under", "correct_score", "first_goal", "goal_minute", "all"],
    )
    parser.add_argument("--db-path", default=None, help="Override SQLite path (default: data/football_intelligence.db)")
    args = parser.parse_args()

    config = InspectionConfig(
        date_arg=args.date,
        timezone=args.timezone,
        scope=args.scope,  # type: ignore[arg-type]
        limit=max(1, args.limit),
        market=args.market,  # type: ignore[arg-type]
        db_path=args.db_path,
    )
    result = inspect_owner_predictions(config)
    output = sanitize_for_output(format_predictions_output(result, args.output_format))  # type: ignore[arg-type]
    print(output)

    if result.get("status") == "error":
        return 2 if result.get("error") == DB_MISSING_MSG else 1
    if result.get("status") == "empty":
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
