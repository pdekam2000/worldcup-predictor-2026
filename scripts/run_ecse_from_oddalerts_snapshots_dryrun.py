#!/usr/bin/env python3
"""ECSE dry-run from OddAlerts CSV policy odds_snapshots (no production writes)."""

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
from worldcup_predictor.research.oddalerts_ecse_dryrun import (
    PROCESS_DATE,
    REPORT_PATH,
    artifact_paths,
    build_evaluation_preview,
    build_quality_report,
    build_report_markdown,
    dryrun_final_recommendation,
    run_ecse_dryrun_batch,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="ECSE dry-run from OddAlerts CSV snapshots")
    parser.add_argument("--date", default=PROCESS_DATE)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--fixture-list", type=Path, default=None)
    args = parser.parse_args()

    paths = artifact_paths(args.date)
    list_path = args.fixture_list or paths["fixture_list"]
    if not list_path.exists():
        print(f"Missing fixture list: {list_path}. Run list_oddalerts_ecse_ready_fixtures.py first.", file=sys.stderr)
        return 2

    fixture_list = json.loads(list_path.read_text(encoding="utf-8"))
    db_path = get_db_path(get_settings().sqlite_path)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=120)
    conn.row_factory = sqlite3.Row

    ecse_before = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]
    odds_before = conn.execute("SELECT COUNT(*) c FROM odds_snapshots").fetchone()["c"]
    wde_before = conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]

    batch = run_ecse_dryrun_batch(conn, fixture_list, limit=args.limit)
    quality = build_quality_report(batch)
    evaluation = build_evaluation_preview(conn, batch.get("predictions") or [])

    ecse_after = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]
    odds_after = conn.execute("SELECT COUNT(*) c FROM odds_snapshots").fetchone()["c"]
    wde_after = conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]
    conn.close()

    recommendation = dryrun_final_recommendation(batch=batch, quality=quality, evaluation=evaluation)

    summary = {
        "phase": batch.get("phase"),
        "generated_at_utc": batch.get("generated_at_utc"),
        "date_processed": args.date,
        "candidate_count": batch.get("candidate_count"),
        "generated_count": batch.get("generated_count"),
        "failed_count": batch.get("failed_count"),
        "ecse_snapshots_before": ecse_before,
        "ecse_snapshots_after": ecse_after,
        "odds_snapshots_before": odds_before,
        "odds_snapshots_after": odds_after,
        "wde_predictions_before": wde_before,
        "wde_predictions_after": wde_after,
        "final_recommendation": recommendation,
        "failure_reasons": quality.get("failure_reasons"),
    }

    paths["predictions_jsonl"].parent.mkdir(parents=True, exist_ok=True)
    with paths["predictions_jsonl"].open("w", encoding="utf-8") as fh:
        for pred in batch.get("predictions") or []:
            fh.write(json.dumps(pred, ensure_ascii=False) + "\n")

    paths["summary"].write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["quality"].write_text(json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["evaluation"].write_text(json.dumps(evaluation, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_PATH.write_text(
        build_report_markdown(
            fixture_list=fixture_list,
            batch=batch,
            quality=quality,
            evaluation=evaluation,
            validation=None,
            recommendation=recommendation,
        ),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Written: {paths['predictions_jsonl']}")
    print(f"Written: {paths['summary']}")
    print(f"Written: {paths['quality']}")
    print(f"Written: {paths['evaluation']}")
    print(f"Written: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
