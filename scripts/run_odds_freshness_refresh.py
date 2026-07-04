#!/usr/bin/env python3
"""ODDS-FRESHNESS-1 — Safe cache-first odds refresh runner."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.odds.freshness_audit import render_audit_markdown, run_odds_freshness_audit
from worldcup_predictor.odds.freshness_impact import render_impact_markdown, run_freshness_impact_analysis
from worldcup_predictor.odds.freshness_refresh import run_odds_freshness_refresh, write_refresh_artifacts

PHASE = "ODDS-FRESHNESS-1"


def main() -> int:
    parser = argparse.ArgumentParser(description="ODDS-FRESHNESS-1 safe odds refresh")
    parser.add_argument("--date", default="today")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--competition", default=None)
    parser.add_argument("--fixture-id", type=int, default=None)
    parser.add_argument("--mode", choices=("audit", "refresh"), default="audit")
    parser.add_argument("--max-provider-calls", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", default="auto", choices=("auto", "oddalerts", "sportmonks", "api_football"))
    parser.add_argument("--write-audit", action="store_true", help="Also write ODDS_FRESHNESS_1_AUDIT.md")
    parser.add_argument("--write-impact", action="store_true", help="Also write impact analysis")
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()

    settings = get_settings()
    db_path = args.db_path or settings.sqlite_path
    comp_keys = [args.competition] if args.competition else None

    if args.write_audit or args.mode == "audit":
        audit = run_odds_freshness_audit(db_path)
        Path("ODDS_FRESHNESS_1_AUDIT.md").write_text(render_audit_markdown(audit), encoding="utf-8")

    result = run_odds_freshness_refresh(
        date_arg=args.date,
        timezone=args.timezone,
        competition_keys=comp_keys,
        fixture_id=args.fixture_id,
        mode=args.mode,
        max_provider_calls=args.max_provider_calls,
        dry_run=args.dry_run or args.mode == "audit",
        source=args.source,
        settings=settings,
    )
    paths = write_refresh_artifacts(result)

    if args.write_impact:
        impact = run_freshness_impact_analysis(db_path)
        Path("ODDS_FRESHNESS_1_IMPACT_ANALYSIS.md").write_text(render_impact_markdown(impact), encoding="utf-8")

    print(
        json.dumps(
            {
                "phase": PHASE,
                "mode": result.mode,
                "dry_run": result.dry_run,
                "fixtures_scanned": result.fixtures_scanned,
                "would_refresh": result.would_refresh,
                "refreshed": result.refreshed,
                "artifacts": paths,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
