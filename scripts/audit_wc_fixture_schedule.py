#!/usr/bin/env python3
"""FIXTURE-SYNC-1 Part A — Audit WC fixture schedule (read-only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.owner_daily.wc_schedule_sync import (
    PHASE,
    render_audit_markdown,
    resolve_competition_key,
    run_wc_schedule_audit,
)

OUTPUT_MD = ROOT / "FIXTURE_SYNC_1_AUDIT.md"
OUTPUT_JSON = ROOT / "artifacts" / "fixture_sync" / "fixture_sync_1_audit.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="FIXTURE-SYNC-1 WC fixture schedule audit")
    parser.add_argument("--competition", default="wc")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--upcoming-limit", type=int, default=20)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--write-md", default=str(OUTPUT_MD))
    args = parser.parse_args()

    settings = get_settings()
    comp = resolve_competition_key(args.competition)
    audit = run_wc_schedule_audit(
        db_path=args.db_path or settings.sqlite_path,
        competition_key=comp,
        tz_name=args.timezone,
        upcoming_limit=args.upcoming_limit,
    )

    md_path = Path(args.write_md)
    md_path.write_text(render_audit_markdown(audit), encoding="utf-8")
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(audit.to_dict(), indent=2), encoding="utf-8")

    print(json.dumps({"phase": PHASE, "audit_md": str(md_path), "audit_json": str(OUTPUT_JSON), **audit.to_dict()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
