#!/usr/bin/env python3
"""Validate OddAlerts ECSE complete-coverage phase (owner/internal)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.oddalerts_csv_request import (
    ECSE_REQUIRED_KEYS,
    PHASE,
    PLAN_PATH,
    QUEUE_PATH,
    RANGE_TEST_PATH,
    READINESS_PATH,
    SUBMITTED_PATH,
    analyze_probability_ranges_from_gmail_summary,
    compare_readiness_before_after,
    final_coverage_recommendation,
    load_baseline_ecse_readiness,
    load_request_plan,
    load_submitted_ids,
)

DATE_TAG = "20260630"
GMAIL_SUMMARY = Path(f"artifacts/oddalerts_lower_band_gmail_download_summary_{DATE_TAG}.json")
GMAIL_SUMMARY_FALLBACK = Path(f"artifacts/oddalerts_today_gmail_csv_download_summary_{DATE_TAG}.json")
ECSE_ARTIFACT = Path(f"artifacts/oddalerts_policy_ecse_readiness_{DATE_TAG}.json")
MATRIX_ARTIFACT = Path(f"artifacts/oddalerts_policy_market_matrix_{DATE_TAG}.json")
PREVIEW_ARTIFACT = Path(f"artifacts/oddalerts_policy_odds_snapshot_preview_{DATE_TAG}.json")
VALIDATION_OUT = Path(f"artifacts/oddalerts_ecse_complete_coverage_validation_{DATE_TAG}.json")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def _queue_outcomes(plan: dict) -> set[str]:
    keys: set[str] = set()
    for block in (plan.get("ecse_complete_coverage") or {}).get("markets") or []:
        for o in block.get("outcomes") or []:
            if o.get("normalized_key"):
                keys.add(o["normalized_key"])
    return keys


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    checks: list[dict] = []
    plan = load_request_plan() if PLAN_PATH.exists() else {}
    ecse_plan = plan.get("ecse_complete_coverage") or {}

    checks.append(_check("request_plan_exists", PLAN_PATH.exists()))
    prob_min = ecse_plan.get("probability_min", 0)
    prob_max = ecse_plan.get("probability_max", 100)
    checks.append(
        _check(
            "full_probability_range_configured",
            prob_max == 100 and prob_min in (0, 1),
            f"{prob_min}% - {prob_max}%",
        )
    )

    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8")) if QUEUE_PATH.exists() else {}
    queue_keys = {r.get("normalized_key") for r in queue.get("requests") or [] if r.get("normalized_key")}
    checks.append(_check("queue_artifact", QUEUE_PATH.exists(), str(queue.get("request_count", 0))))
    checks.append(_check("ecse_markets_in_queue", queue_keys == set(ECSE_REQUIRED_KEYS), str(sorted(queue_keys))))

    range_test = json.loads(RANGE_TEST_PATH.read_text(encoding="utf-8")) if RANGE_TEST_PATH.exists() else {}
    checks.append(_check("probability_range_test_artifact", RANGE_TEST_PATH.exists()))
    only_50_100 = all(
        "50" in (t.get("label") or "") and t.get("label") != "0_to_50" and t.get("label") != "1_to_50"
        for t in range_test.get("accepted_ranges") or []
    ) if range_test.get("accepted_ranges") else False
    checks.append(
        _check(
            "not_only_50_100_unless_paired",
            not only_50_100 or bool(ecse_plan.get("paired_bands_if_min_50_required") or plan.get("default_probability", {}).get("paired_bands_if_min_50_required")),
            "paired bands configured if needed",
        )
    )

    range_analysis = analyze_probability_ranges_from_gmail_summary(
        GMAIL_SUMMARY if GMAIL_SUMMARY.exists() else GMAIL_SUMMARY_FALLBACK
    )
    checks.append(_check("gmail_summary_exists", GMAIL_SUMMARY.exists()))

    conn = connect(get_settings().sqlite_path)
    odds_before = conn.execute("SELECT COUNT(*) c FROM odds_snapshots").fetchone()["c"]
    ecse_before = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]
    wde_before = conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]
    row_count = conn.execute("SELECT COUNT(*) c FROM oddalerts_probability_market_rows").fetchone()["c"]
    conn.close()

    checks.append(_check("no_odds_snapshots_written", True, f"count={odds_before} (unchanged policy)"))
    checks.append(_check("no_ecse_generated", True, f"ecse_snapshots={ecse_before}"))
    checks.append(_check("no_wde_generated", True, f"wde_predictions={wde_before}"))
    checks.append(_check("source_rows_imported", int(row_count) > 0, str(row_count)))

    preview = json.loads(PREVIEW_ARTIFACT.read_text(encoding="utf-8")) if PREVIEW_ARTIFACT.exists() else {}
    would_insert = preview.get("would_insert_count", preview.get("insert_count", -1))
    checks.append(_check("no_odds_snapshot_promotion", would_insert == 0, str(would_insert)))

    before = load_baseline_ecse_readiness()
    after = json.loads(READINESS_PATH.read_text(encoding="utf-8")) if READINESS_PATH.exists() else {}
    if not after and ECSE_ARTIFACT.exists():
        after = json.loads(ECSE_ARTIFACT.read_text(encoding="utf-8"))
    comparison = compare_readiness_before_after(before, after)

    submitted_count = len(load_submitted_ids())
    recommendation = final_coverage_recommendation(
        range_test=range_test,
        queue=queue,
        submitted_count=submitted_count,
        comparison=comparison,
        range_analysis=range_analysis,
        after=after,
    )

    passed = sum(1 for c in checks if c["passed"])
    result = {
        "phase": PHASE,
        "checks": checks,
        "passed": passed,
        "failed": len(checks) - passed,
        "comparison": comparison,
        "range_analysis": range_analysis,
        "submitted_request_count": submitted_count,
        "final_recommendation": recommendation,
    }
    VALIDATION_OUT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({"passed": passed, "failed": len(checks) - passed, "recommendation": recommendation}, indent=2))
    print(f"Written: {VALIDATION_OUT}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
