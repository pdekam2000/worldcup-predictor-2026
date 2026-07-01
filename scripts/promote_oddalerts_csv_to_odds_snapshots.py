#!/usr/bin/env python3
"""Promote OddAlerts CSV policy odds into odds_snapshots (controlled write)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.data_import.oddalerts_bookmaker_policy import PROCESS_DATE
from worldcup_predictor.data_import.oddalerts_csv_promotion_write import (
    GENERATED_FROM,
    REPORT_PATH,
    build_post_write_ecse_readiness,
    build_write_report_markdown,
    create_pre_write_backup,
    run_promotion_write,
    write_artifact_paths,
    write_final_recommendation,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote OddAlerts CSV policy to odds_snapshots")
    parser.add_argument("--date", default=PROCESS_DATE)
    parser.add_argument("--write", action="store_true", help="Execute controlled write (default is dry-run preview)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--fixture-id", type=int, default=None)
    parser.add_argument("--allow-enrich-placeholders", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--no-overwrite-fresh-provider", action="store_true", default=True)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    write_mode = bool(args.write)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    paths = write_artifact_paths(args.date)
    if not paths["dryrun"].exists():
        print(f"Missing dry-run artifact: {paths['dryrun']}", file=sys.stderr)
        return 2

    dryrun = json.loads(paths["dryrun"].read_text(encoding="utf-8"))
    db_path = get_db_path(get_settings().sqlite_path)
    backup_info: dict | None = None

    if write_mode:
        logging.info("Creating pre-write backup...")
        backup_info = create_pre_write_backup(db_path)
        if not backup_info.get("backup_success"):
            print(json.dumps({"error": "backup_failed", "backup": backup_info}, indent=2), file=sys.stderr)
            result = {
                "phase": "ODDALERTS-CSV-PROMOTION-3",
                "write_mode": True,
                "backup": backup_info,
                "final_recommendation": "WRITE_ABORTED_BACKUP_FAILED",
            }
            paths["write_out"].parent.mkdir(parents=True, exist_ok=True)
            paths["write_out"].write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            REPORT_PATH.write_text(build_write_report_markdown(result), encoding="utf-8")
            return 1
        logging.info("Backup OK: %s (%s bytes)", backup_info["backup_path"], backup_info["backup_size_bytes"])

    conn = connect(get_settings().sqlite_path)
    result = run_promotion_write(
        conn,
        dryrun=dryrun,
        write=write_mode,
        fixture_id=args.fixture_id,
        limit=args.limit,
        allow_enrich_placeholders=args.allow_enrich_placeholders,
        no_overwrite_fresh_provider=args.no_overwrite_fresh_provider,
        batch_size=args.batch_size,
        process_date=args.date,
        backup_info=backup_info,
    )

    written_ids = [int(w["fixture_id"]) for w in (result.get("written_fixtures") or []) if w.get("fixture_id")]
    if write_mode:
        db_ids = conn.execute(
            """
            SELECT DISTINCT fixture_id FROM odds_snapshots
            WHERE payload_json LIKE ?
            """,
            (f'%{GENERATED_FROM}%',),
        ).fetchall()
        if db_ids:
            written_ids = sorted({int(r[0]) for r in db_ids})

    ecse = build_post_write_ecse_readiness(conn, written_ids)
    conn.close()

    result["final_recommendation"] = write_final_recommendation(result)
    if write_mode and ecse.get("fixtures_ecse_odds_ready_count", 0) == result.get("inserted_count", 0) + result.get("enriched_count", 0):
        if result["final_recommendation"] == "ODDALERTS_ODDS_SNAPSHOTS_WRITTEN":
            result["ecse_next_step"] = "READY_FOR_ECSE_GENERATION_DRYRUN"

    paths["write_out"].parent.mkdir(parents=True, exist_ok=True)
    paths["write_out"].write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["post_ecse"].write_text(json.dumps(ecse, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_PATH.write_text(build_write_report_markdown(result, ecse=ecse), encoding="utf-8")

    print(
        json.dumps(
            {
                "write_mode": write_mode,
                "inserted_count": result.get("inserted_count"),
                "enriched_count": result.get("enriched_count"),
                "skipped_count": result.get("skipped_count"),
                "odds_snapshots_delta": result.get("odds_snapshots_delta"),
                "final_recommendation": result.get("final_recommendation"),
                "backup_path": (backup_info or {}).get("backup_path"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"Written: {paths['write_out']}")
    print(f"Written: {paths['post_ecse']}")
    print(f"Written: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
