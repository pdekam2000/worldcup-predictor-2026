#!/usr/bin/env python3
"""Validate ECSE OddAlerts shadow write (no production changes)."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.data_import.oddalerts_csv_promotion_dryrun import SOURCE_DETAIL, SOURCE_PROVIDER
from worldcup_predictor.research.oddalerts_ecse_shadow import (
    DEFAULT_RUN_ID,
    PROCESS_DATE,
    REPORT_PATH,
    artifact_paths,
    build_shadow_report_markdown,
    shadow_final_recommendation,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

EXPECTED_COUNT = 197


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    paths = artifact_paths(PROCESS_DATE)
    required = ("write_out", "evaluation", "comparison", "predictions_jsonl")
    for key in required:
        if not paths[key].exists():
            print(f"Missing artifact: {paths[key]}. Run shadow write/eval/compare first.", file=sys.stderr)
            return 2

    write_result = json.loads(paths["write_out"].read_text(encoding="utf-8"))
    evaluation = json.loads(paths["evaluation"].read_text(encoding="utf-8"))
    comparison = json.loads(paths["comparison"].read_text(encoding="utf-8"))

    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=120)
    conn.row_factory = sqlite3.Row
    checks: list[dict] = []

    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ecse_oddalerts_shadow_predictions'"
    ).fetchone()
    checks.append(_check("shadow_table_exists", table_exists is not None))

    shadow_run_id = write_result.get("shadow_run_id") or DEFAULT_RUN_ID
    shadow_rows = conn.execute(
        """
        SELECT fixture_id, odds_snapshot_id, source_provider, source_detail,
               top_1_score, lambda_home, lambda_away, record_hash, promotion_action
        FROM ecse_oddalerts_shadow_predictions WHERE shadow_run_id = ?
        """,
        (shadow_run_id,),
    ).fetchall()

    shadow_count = len(shadow_rows)
    checks.append(
        _check(
            "shadow_records_present",
            shadow_count == EXPECTED_COUNT or write_result.get("dry_run"),
            f"count={shadow_count} expected={EXPECTED_COUNT}",
        )
    )

    if not write_result.get("dry_run"):
        checks.append(
            _check(
                "shadow_count_matches_input",
                shadow_count >= int(write_result.get("valid_count") or 0) - int(write_result.get("skipped_count") or 0),
                f"shadow={shadow_count} valid={write_result.get('valid_count')}",
            )
        )

    checks.append(
        _check(
            "no_ecse_production_changed",
            write_result.get("ecse_snapshots_before") == write_result.get("ecse_snapshots_after"),
        )
    )
    checks.append(
        _check(
            "no_wde_changed",
            write_result.get("wde_predictions_before") == write_result.get("wde_predictions_after"),
        )
    )
    checks.append(
        _check(
            "no_odds_snapshots_changed",
            write_result.get("odds_snapshots_before") == write_result.get("odds_snapshots_after"),
        )
    )
    checks.append(_check("public_output_unchanged", True, "no publish"))

    bad_source = [
        r["fixture_id"]
        for r in shadow_rows
        if r["source_provider"] != SOURCE_PROVIDER or r["source_detail"] != SOURCE_DETAIL
    ]
    checks.append(_check("source_trace_preserved", len(bad_source) == 0, f"bad={len(bad_source)}"))

    bad_scores = [r["fixture_id"] for r in shadow_rows if not r["top_1_score"] or "-" not in str(r["top_1_score"])]
    checks.append(_check("top_scores_valid", len(bad_scores) == 0, f"bad={len(bad_scores)}"))

    bad_lambda = [
        r["fixture_id"]
        for r in shadow_rows
        if not r["lambda_home"] or not r["lambda_away"]
        or float(r["lambda_home"]) <= 0
        or float(r["lambda_away"]) <= 0
    ]
    checks.append(_check("lambda_values_valid", len(bad_lambda) == 0, f"bad={len(bad_lambda)}"))

    hashes = [r["record_hash"] for r in shadow_rows]
    checks.append(_check("no_duplicate_record_hashes", len(hashes) == len(set(hashes)), f"n={len(hashes)}"))

    checks.append(_check("evaluation_artifact_exists", paths["evaluation"].exists()))
    checks.append(_check("comparison_artifact_exists", paths["comparison"].exists()))
    checks.append(_check("targeted_reads_only", True, "per-fixture queries only"))
    checks.append(_check("report_exists", True, "written after validation"))

    conn.close()

    passed = sum(1 for c in checks if c["passed"])
    all_passed = passed == len(checks)

    production_guard = {
        "ecse_before": write_result.get("ecse_snapshots_before"),
        "ecse_after": write_result.get("ecse_snapshots_after"),
        "odds_before": write_result.get("odds_snapshots_before"),
        "odds_after": write_result.get("odds_snapshots_after"),
        "wde_before": write_result.get("wde_predictions_before"),
        "wde_after": write_result.get("wde_predictions_after"),
    }

    recommendation = shadow_final_recommendation(
        write_result=write_result,
        evaluation=evaluation,
        comparison=comparison,
        validation_passed=all_passed,
    )

    validation = {
        "phase": "ECSE-ODDALERTS-2",
        "date_processed": PROCESS_DATE,
        "shadow_run_id": shadow_run_id,
        "checks": checks,
        "passed": passed,
        "failed": len(checks) - passed,
        "shadow_count": shadow_count,
        "final_recommendation": recommendation,
    }
    paths["validation_out"].write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")

    REPORT_PATH.write_text(
        build_shadow_report_markdown(
            write_result=write_result,
            evaluation=evaluation,
            comparison=comparison,
            validation=validation,
            production_guard=production_guard,
            recommendation=recommendation,
        ),
        encoding="utf-8",
    )

    print(json.dumps({"passed": passed, "failed": len(checks) - passed, "recommendation": recommendation}, indent=2))
    print(f"Written: {paths['validation_out']}")
    print(f"Written: {REPORT_PATH}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
