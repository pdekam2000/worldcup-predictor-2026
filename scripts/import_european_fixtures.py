#!/usr/bin/env python3
"""PHASE EURO-A — Import upcoming European fixtures (feed only, no WDE/ECSE)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.euro_feed_registry import EURO_A_TARGET_KEYS, list_euro_feed_specs
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.data_import.european_fixture_feed import (
    import_european_fixtures,
    verify_domestic_results,
)

SUMMARY_PATH = ROOT / "artifacts" / "euro_a_fixture_feed_summary.json"


def _load_summary() -> dict:
    if not SUMMARY_PATH.exists():
        return {}
    try:
        return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _coverage_blocks(repo: FootballIntelligenceRepository, keys: list[str]) -> dict[str, dict]:
    return {key: repo.count_competition_coverage(key) for key in keys}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="EURO-A upcoming fixture feed import")
    parser.add_argument(
        "--competitions",
        nargs="+",
        default=list(EURO_A_TARGET_KEYS),
        help="Competition keys from registry (default: all EURO-A targets)",
    )
    parser.add_argument(
        "--days-ahead",
        type=int,
        default=30,
        help="Import window from today through N days ahead (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and report without persisting",
    )
    parser.add_argument(
        "--no-sportmonks",
        action="store_true",
        help="Skip Sportmonks supplementary fetch",
    )
    parser.add_argument(
        "--summary",
        type=str,
        default=str(SUMMARY_PATH),
        help="Summary JSON output path",
    )
    args = parser.parse_args()

    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    keys = list(args.competitions)
    before = _coverage_blocks(repo, keys)

    report = import_european_fixtures(
        competition_keys=keys,
        days_ahead=args.days_ahead,
        dry_run=args.dry_run,
        settings=settings,
        include_sportmonks=not args.no_sportmonks,
        repository=repo,
    )
    after = _coverage_blocks(repo, keys)
    repo.close()

    competitions_out: list[dict] = []
    by_key: dict[str, list[dict]] = {}
    for block in report.by_competition:
        by_key.setdefault(block["competition_key"], []).append(block)

    for key in keys:
        blocks = by_key.get(key, [])
        imported = sum(int(b.get("upcoming_imported") or 0) for b in blocks)
        updated = sum(int(b.get("fixtures_synced") or 0) for b in blocks)
        errors: list[str] = []
        for b in blocks:
            errors.extend(b.get("errors") or [])
        competitions_out.append(
            {
                "phase": "EURO-A",
                "competition_key": key,
                "before": before.get(key, {}),
                "after": after.get(key, {}),
                "imported": imported,
                "updated": updated,
                "providers": blocks,
                "errors": errors,
            }
        )

    domestic_verification = {
        key: verify_domestic_results(key, settings=settings, sample_size=20)
        for key in ("premier_league", "bundesliga")
        if key in keys or key in EURO_A_TARGET_KEYS
    }

    payload = {
        "fixture_import": {
            **report.to_dict(),
            "competitions": competitions_out,
            "completed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        },
        "registry": {
            "competitions": [s.to_dict() for s in list_euro_feed_specs()],
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        },
        "domestic_verification": domestic_verification,
    }

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_summary() if summary_path == SUMMARY_PATH else {}
    existing.update(payload)
    summary_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\nWrote {summary_path}")

    has_hard_failures = any(
        "not configured" in err.lower() or "request failed" in err.lower()
        for err in report.provider_errors
    )
    if has_hard_failures and report.upcoming_imported == 0 and not args.dry_run:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
