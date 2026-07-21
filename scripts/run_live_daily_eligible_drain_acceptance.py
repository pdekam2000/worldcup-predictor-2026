#!/usr/bin/env python3
"""Part I — Live acceptance for current-day eligible fixture drain."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/opt/worldcup-predictor")
if not (ROOT / "data").is_dir():
    ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("ENV_FILE", str(ROOT / ".env.production"))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.gpt_actions.owner_scope import competition_keys_for_scope
from worldcup_predictor.owner_daily.fixture_discovery import discover_daily_fixtures, resolve_target_date
from worldcup_predictor.owner_daily.pipeline.drain_ledger import (
    BLOCKED,
    FAILED_FINAL,
    FROZEN,
    POST_KICKOFF_SKIPPED,
    DrainLedger,
)
from worldcup_predictor.owner_daily.pipeline.drain_runner import DrainConfig, drain_daily_queue

ART = ROOT / "artifacts" / "daily_eligible_drain_recovery" / "live_acceptance"


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    date_arg = "today"
    if len(sys.argv) > 1:
        date_arg = sys.argv[1]
    report_date = resolve_target_date(date_arg, "Europe/Vienna").isoformat()
    keys = competition_keys_for_scope("owner")
    disc = discover_daily_fixtures(
        date_arg=date_arg,
        timezone="Europe/Vienna",
        competition_keys=keys,
        limit=0,
        settings=settings,
        fetch_if_missing=True,
        dry_run=False,
    )
    with DrainLedger() as ledger:
        result = drain_daily_queue(
            disc.fixtures,
            config=DrainConfig(
                report_date=report_date,
                concurrency=1,
                simulate_only=False,
                dry_run=False,
                strict_fresh_odds=False,
            ),
            ledger=ledger,
            settings=settings,
        )
        rows = ledger.export_day(report_date)
        rec = ledger.reconcile(report_date)

    eligibleish = [
        r
        for r in rows
        if r["queue_state"]
        in (FROZEN, BLOCKED, FAILED_FINAL, POST_KICKOFF_SKIPPED, "COMPLETED")
        or r["queue_state"] not in ("DISCOVERED",)
    ]
    # Acceptance equation uses blocked + frozen + failed_final + post_kickoff
    # COMPLETED (partial) counts toward accounted (not silent omit)
    frozen = sum(1 for r in rows if r["queue_state"] == FROZEN)
    blocked = sum(1 for r in rows if r["queue_state"] == BLOCKED)
    failed_final = sum(1 for r in rows if r["queue_state"] == FAILED_FINAL)
    post = sum(1 for r in rows if r["queue_state"] == POST_KICKOFF_SKIPPED)
    completed = sum(1 for r in rows if r["queue_state"] == "COMPLETED")
    accounted = frozen + blocked + failed_final + post + completed
    eligible_count = len(rows)
    equation_ok = accounted == eligible_count and int(rec.get("pending") or 0) == 0

    out = {
        "report_date": report_date,
        "discovered": len(disc.fixtures),
        "eligible_count": eligible_count,
        "frozen": frozen,
        "blocked": blocked,
        "failed_final": failed_final,
        "post_kickoff_skipped": post,
        "completed_partial": completed,
        "accounted": accounted,
        "equation": "eligible = frozen + blocked + failed_final + post_kickoff_skipped (+ completed_partial)",
        "equation_ok": equation_ok,
        "reconcile": rec,
        "items": [
            {
                "fixture_id": r["fixture_id"],
                "scope": r["scope"],
                "queue_state": r["queue_state"],
                "block_reason": r["block_reason"],
                "failure_code": r["failure_code"],
                "freeze_id": r["freeze_id"],
                "prediction_status": r["prediction_status"],
            }
            for r in rows
        ],
        "errors": result.errors,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    path = ART / f"live_acceptance_{report_date}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "report_date": report_date,
                "eligible_count": eligible_count,
                "frozen": frozen,
                "blocked": blocked,
                "failed_final": failed_final,
                "post_kickoff_skipped": post,
                "completed_partial": completed,
                "equation_ok": equation_ok,
                "artifact": str(path),
            },
            indent=2,
        )
    )
    return 0 if equation_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
