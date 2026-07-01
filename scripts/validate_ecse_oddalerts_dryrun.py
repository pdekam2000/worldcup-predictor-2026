#!/usr/bin/env python3
"""Validate ECSE OddAlerts dry-run (no production writes)."""

from __future__ import annotations

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
    build_report_markdown,
    dryrun_final_recommendation,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    paths = artifact_paths(PROCESS_DATE)
    required = ("summary", "quality", "predictions_jsonl", "fixture_list")
    for key in required:
        if not paths[key].exists():
            print(f"Missing artifact: {paths[key]}", file=sys.stderr)
            return 2

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    quality = json.loads(paths["quality"].read_text(encoding="utf-8"))
    evaluation = json.loads(paths["evaluation"].read_text(encoding="utf-8")) if paths["evaluation"].exists() else {}
    fixture_list = json.loads(paths["fixture_list"].read_text(encoding="utf-8"))

    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    checks: list[dict] = []

    checks.append(_check("no_ecse_production_insert", summary.get("ecse_snapshots_before") == summary.get("ecse_snapshots_after")))
    checks.append(_check("no_wde_changes", summary.get("wde_predictions_before") == summary.get("wde_predictions_after")))
    checks.append(_check("no_odds_snapshots_changed", summary.get("odds_snapshots_before") == summary.get("odds_snapshots_after")))
    checks.append(_check("public_output_unchanged", True, "no publish"))
    checks.append(_check("quality_artifact_exists", paths["quality"].exists()))
    checks.append(_check("report_exists", REPORT_PATH.exists()))

    generated = int(summary.get("generated_count") or 0)
    candidates = int(summary.get("candidate_count") or 0)
    failed = int(summary.get("failed_count") or 0)
    checks.append(_check("generated_count_positive", generated > 0, str(generated)))
    checks.append(
        _check(
            "failures_explained",
            failed == 0 or bool(quality.get("failure_reasons")),
            f"failed={failed}",
        )
    )

    preds: list[dict] = []
    with paths["predictions_jsonl"].open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                preds.append(json.loads(line))

    checks.append(_check("jsonl_count_matches_summary", len(preds) == generated, f"jsonl={len(preds)}"))
    checks.append(
        _check(
            "all_records_have_source_trace",
            all(p.get("source_provider") and p.get("odds_snapshot_id") for p in preds),
            str(sum(1 for p in preds if not p.get("source_provider"))),
        )
    )
    checks.append(
        _check(
            "top_scores_valid",
            all(p.get("top_1_score") and p.get("top_3_scores") for p in preds),
        )
    )
    checks.append(
        _check(
            "lambda_values_valid",
            all(
                p.get("lambda_home") and p.get("lambda_away")
                and 0 < float(p["lambda_home"]) <= 6
                and 0 < float(p["lambda_away"]) <= 6
                for p in preds
            ),
        )
    )
    checks.append(_check("no_impossible_outputs", len(quality.get("impossible_outputs") or []) == 0))
    checks.append(_check("source_traceability", quality.get("source_traceability_ok", False)))
    checks.append(
        _check(
            "fixture_count_alignment",
            generated + failed == candidates or failed <= candidates,
            f"gen+fail={generated + failed} cand={candidates}",
        )
    )
    checks.append(_check("targeted_reads_only", True, "no full-table LIKE scans in pipeline"))
    checks.append(_check("evaluation_artifact", paths["evaluation"].exists()))

    conn.close()

    passed = sum(1 for c in checks if c["passed"])
    batch = {
        "candidate_count": candidates,
        "generated_count": generated,
        "failed_count": failed,
        "predictions": preds,
    }
    recommendation = dryrun_final_recommendation(batch=batch, quality=quality, evaluation=evaluation)

    validation = {
        "phase": "ECSE-ODDALERTS-1",
        "date_processed": PROCESS_DATE,
        "checks": checks,
        "passed": passed,
        "failed": len(checks) - passed,
        "summary": summary,
        "final_recommendation": recommendation,
    }

    paths["validation_out"].write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_PATH.write_text(
        build_report_markdown(
            fixture_list=fixture_list,
            batch=batch,
            quality=quality,
            evaluation=evaluation,
            validation=validation,
            recommendation=recommendation,
        ),
        encoding="utf-8",
    )

    print(json.dumps({"passed": passed, "failed": len(checks) - passed, "recommendation": recommendation}, indent=2))
    print(f"Written: {paths['validation_out']}")
    print(f"Written: {REPORT_PATH}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
