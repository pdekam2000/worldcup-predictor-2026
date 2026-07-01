#!/usr/bin/env python3
"""PHASE EURO-C4 Part B — Build UEFA OddAlerts crosswalk."""

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
from worldcup_predictor.owner.euro_c4_oddalerts import CROSSWALK_PATH, build_uefa_oddalerts_crosswalk

DEFAULT_OUT = ROOT / "artifacts" / "euro_c4_oddalerts_crosswalk.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="EURO-C4 OddAlerts crosswalk builder")
    parser.add_argument("--competitions", nargs="+", default=list(UEFA_CUP_KEYS))
    parser.add_argument("--days-ahead", type=int, default=30)
    parser.add_argument("--max-api-calls", type=int, default=50)
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUT))
    args = parser.parse_args()

    conn = connect(get_settings().sqlite_path)
    report = build_uefa_oddalerts_crosswalk(
        conn,
        competition_keys=list(args.competitions),
        days_ahead=args.days_ahead,
        max_api_calls=args.max_api_calls,
    )
    conn.close()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"EURO-C4 crosswalk: {report['accepted_count']} accepted / "
        f"{report['api_fixture_count']} API fixtures"
    )
    print(f"Rejected: {report['rejected_count']} | OddAlerts pool: {report['oddalerts_pool_size']}")
    print(f"Provider calls: {report.get('provider_calls')}")
    print(f"Written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
