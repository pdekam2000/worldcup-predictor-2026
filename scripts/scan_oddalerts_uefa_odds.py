#!/usr/bin/env python3
"""PHASE EURO-C4 Part C — Direct OddAlerts odds availability scan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.owner.euro_c4_oddalerts import AVAILABILITY_PATH, scan_oddalerts_uefa_odds

DEFAULT_OUT = ROOT / "artifacts" / "euro_c4_oddalerts_odds_availability.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="EURO-C4 OddAlerts odds scan")
    parser.add_argument("--max-api-calls", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUT))
    args = parser.parse_args()

    conn = connect(get_settings().sqlite_path)
    report = scan_oddalerts_uefa_odds(
        conn,
        max_api_calls=args.max_api_calls,
        dry_run=args.dry_run,
    )
    conn.close()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Fixtures scanned: {report['fixtures_scanned']}")
    print(f"Market coverage: {report.get('market_coverage')}")
    print(f"Parser gaps: {report.get('parser_gap_count')} | Provider empty: {report.get('provider_empty_count')}")
    print(f"Provider calls: {report.get('provider_calls')}")
    print(f"Written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
