#!/usr/bin/env python3
"""Phase 36B — invalidate and refresh provider-env-missing placeholder predictions."""

from __future__ import annotations

import argparse
import json
import runpy
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

from worldcup_predictor.automation.worldcup_background.prediction_runner import run_and_store_prediction
from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore
from worldcup_predictor.automation.worldcup_background.prediction_store_guard import assert_can_run_production_prediction
from worldcup_predictor.automation.worldcup_background.stale_prediction_policy import (
    INVALIDATED_REASON_PROVIDER_ENV,
    should_invalidate_stored_row,
)
from worldcup_predictor.config.provider_readiness import provider_diagnostic
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def backup_sqlite(settings) -> Path:
    src = Path(settings.sqlite_path or "data/football_intelligence.db")
    backup_dir = Path("backups") / f"phase36b-repair-{_utc_stamp()}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / src.name
    if src.exists():
        shutil.copy2(src, dest)
    manifest = {
        "backup_dir": str(backup_dir.resolve()),
        "sqlite": str(dest.resolve()) if dest.exists() else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return backup_dir


def find_bad_rows(repo: FootballIntelligenceRepository) -> list[dict]:
    bad: list[dict] = []
    for row in repo.list_worldcup_stored_prediction_rows(include_inactive=True):
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except json.JSONDecodeError:
            continue
        should, reason = should_invalidate_stored_row(payload, source=str(row.get("source") or ""))
        if should:
            bad.append(
                {
                    "fixture_id": row.get("fixture_id"),
                    "source": row.get("source"),
                    "confidence": payload.get("confidence"),
                    "generated_by": payload.get("generated_by"),
                    "reason": reason,
                    "is_active": row.get("is_active", 1),
                }
            )
    return bad


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 36B placeholder prediction repair")
    parser.add_argument("--fixture-id", type=int, action="append", dest="fixture_ids")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-backup", action="store_true")
    args = parser.parse_args()

    get_settings.cache_clear()
    settings = get_settings()
    assert_can_run_production_prediction(settings)

    diag = provider_diagnostic(settings)
    print(json.dumps({"provider_diagnostic": diag}, indent=2))

    backup_dir = None
    if not args.skip_backup and not args.dry_run:
        backup_dir = backup_sqlite(settings)
        print(f"backup_path={backup_dir.resolve()}")

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    bad_rows = find_bad_rows(repo)
    if args.fixture_ids:
        wanted = set(args.fixture_ids)
        bad_rows = [r for r in bad_rows if int(r["fixture_id"]) in wanted]
        for fid in wanted:
            if not any(int(r["fixture_id"]) == fid for r in bad_rows):
                bad_rows.append({"fixture_id": fid, "source": "manual", "reason": INVALIDATED_REASON_PROVIDER_ENV, "confidence": None})

    print(json.dumps({"bad_rows_found": len(bad_rows), "rows": bad_rows}, indent=2))

    invalidated = 0
    refreshed = 0
    results: list[dict] = []

    for row in bad_rows:
        fid = int(row["fixture_id"])
        reason = str(row.get("reason") or INVALIDATED_REASON_PROVIDER_ENV)
        if args.dry_run:
            results.append({"fixture_id": fid, "action": "would_invalidate_and_refresh", "reason": reason})
            continue

        repo.invalidate_worldcup_stored_prediction(fid, reason=reason)
        invalidated += 1

        payload = run_and_store_prediction(
            fid,
            settings=settings,
            source="phase36b_repair",
            record_history=False,
        )
        ok = payload.get("status") != "error"
        if ok:
            refreshed += 1
        results.append(
            {
                "fixture_id": fid,
                "refreshed": ok,
                "confidence": payload.get("confidence"),
                "is_placeholder": payload.get("is_placeholder"),
                "provider_readiness": payload.get("provider_readiness"),
            }
        )
        time.sleep(0.2)

    summary = {
        "invalidated": invalidated,
        "refreshed": refreshed,
        "backup_path": str(backup_dir.resolve()) if backup_dir else None,
        "results": results,
    }
    print(json.dumps(summary, indent=2))
    return 0 if refreshed >= 1 or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
