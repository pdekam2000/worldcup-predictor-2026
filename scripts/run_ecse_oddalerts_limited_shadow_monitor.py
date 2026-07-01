#!/usr/bin/env python3
"""Run ECSE OddAlerts limited shadow monitor (owner/internal)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.research.oddalerts_ecse_monitor import (
    ELIGIBLE_V2,
    artifact_paths,
    discover_monitor_candidates,
    generate_monitor_prediction,
    monitor_run_id,
    write_monitor_records,
)
from worldcup_predictor.research.oddalerts_ecse_segment_calibration import _batch_wde
from worldcup_predictor.research.oddalerts_ecse_segments import SEGMENT_MODEL_V2, load_v2_calibration_context

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPORT_PATH = Path("ECSE_ODDALERTS_LIMITED_SHADOW_MONITOR_REPORT.md")


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date-from", default="2026-07-01")
    parser.add_argument("--date-to", default="2026-07-07")
    parser.add_argument("--write-shadow", action="store_true", default=False)
    parser.add_argument("--only-eligible-v2", action="store_true", default=False)
    args = parser.parse_args()

    paths = artifact_paths(args.date_from, args.date_to)
    run_id = monitor_run_id(args.date_from, args.date_to)
    dry_run = not args.write_shadow

    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(str(db_path), timeout=120)
    conn.row_factory = sqlite3.Row

    ecse_before = _count(conn, "ecse_prediction_snapshots")
    odds_before = _count(conn, "odds_snapshots")
    wde_before = _count(conn, "worldcup_stored_predictions")

    discovery = discover_monitor_candidates(conn, date_from=args.date_from, date_to=args.date_to)
    paths["candidates"].write_text(json.dumps(discovery, indent=2, ensure_ascii=False), encoding="utf-8")

    v2_ctx = load_v2_calibration_context()
    calibration = v2_ctx.get("calibration")
    utility_percentiles = v2_ctx.get("utility_percentiles")

    candidates = discovery.get("candidates") or []
    fixture_ids = [int(c["fixture_id"]) for c in candidates]
    wde_map = _batch_wde(conn, fixture_ids)

    generated: list[dict] = []
    failed: list[dict] = []
    skipped_ineligible: list[dict] = []

    for cand in candidates:
        out = generate_monitor_prediction(
            conn,
            cand,
            calibration=calibration,
            utility_percentiles=utility_percentiles,
            wde_direction=wde_map.get(int(cand["fixture_id"])),
        )
        if out.get("status") != "generated":
            failed.append(out)
            continue
        elig = out["segment_v2"].get("promotion_eligibility_v2")
        if args.only_eligible_v2 and elig not in ELIGIBLE_V2:
            skipped_ineligible.append({"fixture_id": cand["fixture_id"], "eligibility": elig})
            continue
        generated.append({**out, "candidate": cand})

    write_result = write_monitor_records(
        conn,
        generated,
        monitor_run_id_val=run_id,
        dry_run=dry_run,
    )

    ecse_after = _count(conn, "ecse_prediction_snapshots")
    odds_after = _count(conn, "odds_snapshots")
    wde_after = _count(conn, "worldcup_stored_predictions")
    conn.close()

    from collections import Counter

    badge_dist = Counter(g["segment_v2"]["segment_badge_v2"] for g in generated)

    run_out = {
        "phase": "ECSE-ODDALERTS-5",
        "date_from": args.date_from,
        "date_to": args.date_to,
        "monitor_run_id": run_id,
        "segment_model_version": SEGMENT_MODEL_V2,
        "dry_run": dry_run,
        "discovered_count": discovery.get("candidate_count"),
        "generated_count": len(generated) + len(failed),
        "failed_count": len(failed),
        "skipped_ineligible_count": len(skipped_ineligible),
        "eligible_written": write_result,
        "badge_distribution": dict(badge_dist),
        "ecse_snapshots_before": ecse_before,
        "ecse_snapshots_after": ecse_after,
        "odds_snapshots_before": odds_before,
        "odds_snapshots_after": odds_after,
        "wde_predictions_before": wde_before,
        "wde_predictions_after": wde_after,
    }
    paths["run_out"].write_text(json.dumps(run_out, indent=2, ensure_ascii=False), encoding="utf-8")

    paths["report_md"].parent.mkdir(parents=True, exist_ok=True)
    paths["report_md"].write_text(
        f"# ECSE OddAlerts Limited Shadow Monitor\n\n"
        f"Run: `{run_id}`\n\n"
        f"- Discovered: {discovery.get('candidate_count')}\n"
        f"- Generated: {len(generated)}\n"
        f"- Skipped ineligible: {len(skipped_ineligible)}\n"
        f"- Written: {write_result.get('written_count', write_result.get('would_write_count'))}\n",
        encoding="utf-8",
    )
    REPORT_PATH.write_text(paths["report_md"].read_text(encoding="utf-8"), encoding="utf-8")

    print(json.dumps(run_out, indent=2))
    print(f"Written: {paths['run_out']}")
    print(f"Written: {paths['report_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
