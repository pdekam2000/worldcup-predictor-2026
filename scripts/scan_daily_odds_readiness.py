#!/usr/bin/env python3
"""PHASE DAILY-OWNER-2 — Scan daily odds readiness for owner fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_daily.constants import ARTIFACTS_DIR, DAILY_SUPPORTED_COMPETITIONS
from worldcup_predictor.owner_daily.fixture_discovery import resolve_target_date
from worldcup_predictor.owner_daily.odds_import import scan_daily_odds_readiness

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan daily odds readiness (owner/internal)")
    parser.add_argument("--date", default="today")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--competitions", nargs="+", default=list(DAILY_SUPPORTED_COMPETITIONS))
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    report = scan_daily_odds_readiness(
        date_arg=args.date,
        timezone=args.timezone,
        competition_keys=args.competitions,
        limit=args.limit,
    )
    target = resolve_target_date(args.date, args.timezone)
    ymd = target.isoformat().replace("-", "")
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACTS_DIR / f"daily_odds_readiness_{ymd}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({**report, "artifact_path": str(out_path)}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
