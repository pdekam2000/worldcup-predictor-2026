#!/usr/bin/env python3
"""PHASE EURO-C Part A — Scan UEFA odds availability for ECSE enablement."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.owner.euro_c_odds_import import scan_uefa_odds_availability

DEFAULT_OUT = ROOT / "artifacts" / "euro_c_odds_availability_scan.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="EURO-C UEFA odds availability scan")
    parser.add_argument(
        "--competitions",
        nargs="+",
        default=list(UEFA_CUP_KEYS),
        help="UEFA competition keys",
    )
    parser.add_argument("--days-ahead", type=int, default=30)
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUT))
    args = parser.parse_args()

    settings = get_settings()
    conn = connect(settings.sqlite_path)
    report = scan_uefa_odds_availability(
        conn,
        competition_keys=list(args.competitions),
        days_ahead=args.days_ahead,
    )
    conn.close()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"EURO-C scan complete: {report['fixtures_scanned']} fixtures")
    print(f"ECSE-ready: {report['ecse_ready_count']}")
    print(f"Written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
