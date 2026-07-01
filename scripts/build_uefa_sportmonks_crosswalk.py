#!/usr/bin/env python3
"""PHASE EURO-C2 Part A — Build UEFA Sportmonks crosswalk."""

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
from worldcup_predictor.owner.euro_c2_sportmonks_odds import build_uefa_sportmonks_crosswalk

DEFAULT_OUT = ROOT / "artifacts" / "euro_c2_sportmonks_crosswalk.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="EURO-C2 Sportmonks crosswalk builder")
    parser.add_argument("--competitions", nargs="+", default=list(UEFA_CUP_KEYS))
    parser.add_argument("--days-ahead", type=int, default=30)
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUT))
    args = parser.parse_args()

    conn = connect(get_settings().sqlite_path)
    report = build_uefa_sportmonks_crosswalk(
        conn,
        competition_keys=list(args.competitions),
        days_ahead=args.days_ahead,
    )
    conn.close()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"EURO-C2 crosswalk: {report['accepted_count']} accepted / {report['api_fixtures_targeted']} API fixtures")
    print(f"Ambiguous: {report['ambiguous_count']} | No match: {report['no_match_count']}")
    print(f"Written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
