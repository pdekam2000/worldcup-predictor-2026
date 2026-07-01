#!/usr/bin/env python3
"""PHASE EURO-C2 Part B — Scan Sportmonks UEFA odds availability."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.owner.euro_c2_sportmonks_odds import (
    build_uefa_sportmonks_crosswalk,
    scan_crosswalk_odds_availability,
)

CROSSWALK_PATH = ROOT / "artifacts" / "euro_c2_sportmonks_crosswalk.json"
DEFAULT_OUT = ROOT / "artifacts" / "euro_c2_sportmonks_odds_availability.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="EURO-C2 Sportmonks odds availability scan")
    parser.add_argument("--crosswalk", type=str, default=str(CROSSWALK_PATH))
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUT))
    parser.add_argument("--max-api-calls", type=int, default=0)
    parser.add_argument("--cache-first", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    crosswalk_path = Path(args.crosswalk)
    if crosswalk_path.exists():
        crosswalk = json.loads(crosswalk_path.read_text(encoding="utf-8"))
    else:
        conn = connect(get_settings().sqlite_path)
        crosswalk = build_uefa_sportmonks_crosswalk(conn)
        conn.close()
        crosswalk_path.parent.mkdir(parents=True, exist_ok=True)
        crosswalk_path.write_text(json.dumps(crosswalk, ensure_ascii=False, indent=2), encoding="utf-8")

    conn = connect(get_settings().sqlite_path)
    report = scan_crosswalk_odds_availability(
        conn,
        crosswalk,
        settings=get_settings(),
        max_api_calls=args.max_api_calls,
        cache_first=args.cache_first,
        dry_run=args.dry_run,
    )
    conn.close()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"EURO-C2 odds scan: {report['fixtures_with_odds']}/{report['fixtures_scanned']} with odds")
    print(f"ECSE-ready: {report['ecse_ready_count']} | API calls: {report['api_calls_used']}")
    print(f"Written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
