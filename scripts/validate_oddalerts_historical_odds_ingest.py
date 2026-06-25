#!/usr/bin/env python3
"""Validate OddAlerts historical odds ingest (OA-2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def validate(*, league: str | None = None) -> dict:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.connection import connect
    from worldcup_predictor.providers.oddalerts_historical_odds import (
        OddAlertsHistoricalOddsIngester,
        collect_ingest_summary,
        ensure_oddalerts_tables,
    )
    from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient

    settings = get_settings()
    conn = connect(settings.sqlite_path)
    ensure_oddalerts_tables(conn)

    client = OddAlertsClient()
    summary = collect_ingest_summary(conn, league=league)

    map_total = conn.execute("SELECT COUNT(*) FROM oddalerts_fixture_map").fetchone()[0]
    mapped_internal = conn.execute(
        "SELECT COUNT(*) FROM oddalerts_fixture_map WHERE internal_fixture_id IS NOT NULL"
    ).fetchone()[0]
    ingest_states = conn.execute(
        "SELECT stage, COUNT(*) FROM oddalerts_ingest_state GROUP BY stage"
    ).fetchall()
    runs = conn.execute(
        "SELECT league, season, api_calls_used, fixtures_discovered, odds_rows_stored, status, finished_at "
        "FROM oddalerts_ingest_runs ORDER BY id DESC LIMIT 10"
    ).fetchall()

    checks = {
        "api_key_present": bool(client.is_configured),
        "tables_exist": all(
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (t,),
            ).fetchone()
            for t in ("oddalerts_fixture_map", "oddalerts_odds_history", "oddalerts_ingest_state")
        ),
        "fixtures_mapped": map_total > 0,
        "odds_rows_stored": summary["odds_rows_total"] > 0,
        "opening_odds_stored": summary["opening_odds_rows"] > 0,
        "closing_odds_stored": summary["closing_odds_rows"] > 0,
        "peak_odds_stored": summary["peak_odds_rows"] > 0,
        "bookmakers_stored": len(summary["bookmaker_coverage"]) > 0,
        "markets_stored": len(summary["market_coverage"]) > 0,
        "no_duplicate_rows": len(summary["duplicate_rows_sample"]) == 0,
        "resume_state_rows": sum(int(r[1]) for r in ingest_states) > 0,
        "internal_fixture_mapping": mapped_internal > 0,
    }

    passed = sum(1 for v in checks.values() if v)
    return {
        "checks": checks,
        "passed": passed,
        "total_checks": len(checks),
        "all_passed": passed == len(checks),
        "summary": summary,
        "fixture_map_total": int(map_total),
        "internal_mapped_total": int(mapped_internal),
        "ingest_state_counts": {str(r[0]): int(r[1]) for r in ingest_states},
        "recent_runs": [dict(r) for r in runs],
        "db_path": str(settings.sqlite_path),
    }


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--league", default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    result = validate(league=args.league)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Validation: {result['passed']}/{result['total_checks']} checks passed")
        for name, ok in result["checks"].items():
            print(f"  {'PASS' if ok else 'FAIL'} {name}")
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
