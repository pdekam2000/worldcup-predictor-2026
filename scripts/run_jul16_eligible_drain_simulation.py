#!/usr/bin/env python3
"""Part H — Jul 16 eligible fixture drain simulation (no historical freezes)."""
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
from worldcup_predictor.owner_daily.fixture_discovery import discover_daily_fixtures
from worldcup_predictor.owner_daily.pipeline.drain_ledger import TERMINAL_STATES, DrainLedger
from worldcup_predictor.owner_daily.pipeline.drain_runner import DrainConfig, drain_daily_queue

TARGET = "2026-07-16"
ART = ROOT / "artifacts" / "daily_eligible_drain_recovery" / "jul16_simulation"
LEDGER = ART / "jul16_sim_ledger.db"


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    if LEDGER.exists():
        LEDGER.unlink()

    settings = get_settings()
    keys = competition_keys_for_scope("owner")
    disc = discover_daily_fixtures(
        date_arg=TARGET,
        timezone="Europe/Vienna",
        competition_keys=keys,
        limit=0,
        settings=settings,
        fetch_if_missing=False,
        dry_run=True,
    )
    # Eligibility clock: morning of Jul 16 before first kickoff
    as_of = datetime(2026, 7, 16, 4, 0, tzinfo=timezone.utc)
    with DrainLedger(LEDGER) as ledger:
        result = drain_daily_queue(
            disc.fixtures,
            config=DrainConfig(
                report_date=TARGET,
                concurrency=1,
                simulate_only=True,
                dry_run=True,
                eligibility_as_of=as_of,
                ledger_path=LEDGER,
            ),
            ledger=ledger,
            settings=settings,
        )

    rows = result.items
    terminal = [r for r in rows if r.get("queue_state") in TERMINAL_STATES]
    silent = [r for r in rows if r.get("queue_state") not in TERMINAL_STATES]
    out = {
        "target_date": TARGET,
        "discovered": len(disc.fixtures),
        "enqueued": result.enqueued,
        "reconcile": result.reconcile,
        "terminal_count": len(terminal),
        "non_terminal": silent,
        "historical_freezes_created": False,
        "items": rows,
        "errors": result.errors,
        "pass": bool(result.reconcile.get("queue_complete")) and len(silent) == 0 and len(rows) == len(disc.fixtures),
    }
    (ART / "jul16_simulation.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("discovered", "enqueued", "reconcile", "terminal_count", "pass", "errors")}, indent=2))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
