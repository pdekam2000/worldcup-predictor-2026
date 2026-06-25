#!/usr/bin/env python3
"""CLI — OddAlerts historical odds ingest (research/backfill only)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="OddAlerts historical odds ingest (OA-2)")
    p.add_argument("--league", required=True, help="League key e.g. premier_league, champions_league, bundesliga")
    p.add_argument("--season", type=int, required=True, help="Calendar season start year e.g. 2023 for 2023/24")
    p.add_argument("--limit-fixtures", type=int, default=50, help="Max fixtures to ingest")
    p.add_argument("--max-api-calls", type=int, default=100, help="API call budget")
    p.add_argument("--dry-run", action="store_true", help="Discover/map only; no DB writes")
    p.add_argument("--no-resume", dest="resume", action="store_false", help="Re-ingest even if already stored")
    p.set_defaults(resume=True)
    p.add_argument("--discovery-pages", type=int, default=25, help="Max pages to scan for fixture discovery")
    p.add_argument("--json", action="store_true", help="Print JSON summary to stdout")
    return p


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    args = build_parser().parse_args()
    from worldcup_predictor.providers.oddalerts_historical_odds import OddAlertsHistoricalOddsIngester

    ingester = OddAlertsHistoricalOddsIngester()
    if not ingester.is_configured:
        logger.error("ODDALERTS_API_KEY not configured in .env")
        return 1

    result = ingester.run_ingest(
        league=args.league,
        season=args.season,
        limit_fixtures=args.limit_fixtures,
        max_api_calls=args.max_api_calls,
        dry_run=args.dry_run,
        resume=args.resume,
        max_discovery_pages=args.discovery_pages,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        logger.info(
            "league=%s season=%s discovered=%s processed=%s odds_rows=%s api_calls=%s status=%s",
            result.get("league"),
            result.get("season"),
            result.get("fixtures_discovered"),
            result.get("fixtures_processed"),
            result.get("odds_rows_stored"),
            result.get("api_calls_used"),
            result.get("status"),
        )
        mapping = result.get("fixture_mapping") or {}
        logger.info(
            "mapping exact=%s fuzzy=%s unmatched=%s",
            mapping.get("exact"),
            mapping.get("fuzzy"),
            mapping.get("unmatched"),
        )
        if result.get("message"):
            logger.warning("%s", result["message"])
        for err in result.get("errors") or []:
            logger.warning("%s", err)

    return 0 if result.get("status") in ("ok", "partial") else 1


if __name__ == "__main__":
    raise SystemExit(main())
