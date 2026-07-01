#!/usr/bin/env python3
"""PHASE EURO-C4 — Full OddAlerts UEFA odds audit + import pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner.euro_c4_oddalerts import run_euro_c4_pipeline

DEFAULT_SUMMARY = ROOT / "artifacts" / "euro_c4_oddalerts_pipeline_summary.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="EURO-C4 OddAlerts pipeline")
    parser.add_argument("--competitions", nargs="+", default=list(UEFA_CUP_KEYS))
    parser.add_argument("--days-ahead", type=int, default=30)
    parser.add_argument("--max-api-calls", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repo = FootballIntelligenceRepository(get_settings().sqlite_path or None)
    summary = run_euro_c4_pipeline(
        repo,
        competition_keys=list(args.competitions),
        days_ahead=args.days_ahead,
        dry_run=args.dry_run,
        max_api_calls=args.max_api_calls,
        force=args.force,
    )
    repo.close()

    DEFAULT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"EURO-C4 pipeline complete")
    print(f"Token configured: {summary['config_audit'].get('token_configured')}")
    print(f"Crosswalk accepted: {summary['crosswalk_summary'].get('accepted')}")
    print(f"Total OddAlerts calls: {summary.get('total_oddalerts_calls')}")
    print(f"Imported: {summary['import_summary'].get('imported_count')}")
    print(f"Final recommendation: {summary.get('final_recommendation')}")
    print(f"Log: {summary.get('log_path')}")
    print(f"Written: {DEFAULT_SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
