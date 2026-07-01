#!/usr/bin/env python3
"""Run PHASE SAFE-BETS-1 internal high-probability market scanner."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.safe_bets.scanner import run_safe_bets_scan


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE SAFE-BETS-1 market scanner")
    parser.add_argument("--hours", type=int, default=None, help="Upcoming window in hours (default: settings)")
    parser.add_argument("--limit", type=int, default=100, help="Max fixtures to scan")
    parser.add_argument("--dry-run", action="store_true", help="Scan without persisting candidates")
    args = parser.parse_args()

    settings = get_settings()
    hours = args.hours if args.hours is not None else settings.safe_bets_hours
    if args.dry_run:
        settings = settings.model_copy(update={"safe_bets_dry_run": True})

    db_path = get_db_path(settings.sqlite_path)
    conn = connect(db_path)
    try:
        report = run_safe_bets_scan(conn, settings=settings, hours=hours, limit=args.limit)
    finally:
        conn.close()

    print(json.dumps(report.to_dict(), indent=2, default=str))
    out = Path("artifacts/safe_bets_1_latest_scan.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out}")
    return 0 if report.to_dict().get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
