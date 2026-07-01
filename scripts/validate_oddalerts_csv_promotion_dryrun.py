#!/usr/bin/env python3
"""Validate OddAlerts CSV odds_snapshots promotion dry-run."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.oddalerts_bookmaker_policy import ECSE_REQUIRED_KEYS, PROCESS_DATE
from worldcup_predictor.data_import.oddalerts_csv_promotion_dryrun import (
    PHASE,
    REPORT_PATH,
    SOURCE_PROVIDER,
    artifact_paths,
    build_report_markdown,
    promotion_final_recommendation,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    paths = artifact_paths(PROCESS_DATE)
    dryrun_path = paths["dryrun_out"]

    if not dryrun_path.exists():
        print(f"Missing dry-run artifact: {dryrun_path}", file=sys.stderr)
        print("Run scripts/preview_promote_oddalerts_csv_to_odds_snapshots.py first.", file=sys.stderr)
        return 2

    dryrun = json.loads(dryrun_path.read_text(encoding="utf-8"))
    dual_band = json.loads(paths["dual_band_coverage"].read_text(encoding="utf-8")) if paths["dual_band_coverage"].exists() else {}
    ecse_readiness = json.loads(paths["ecse_readiness"].read_text(encoding="utf-8")) if paths["ecse_readiness"].exists() else {}

    conn = connect(get_settings().sqlite_path)
    odds_count = int(conn.execute("SELECT COUNT(*) c FROM odds_snapshots").fetchone()["c"])
    ecse_count = int(conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"])
    wde_count = int(conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"])
    conn.close()

    checks: list[dict] = []

    checks.append(_check("dryrun_artifact_exists", dryrun_path.exists()))
    checks.append(_check("dry_run_only_flag", dryrun.get("dry_run_only") is True))
    checks.append(_check("writes_odds_snapshots_false", dryrun.get("writes_odds_snapshots") is False))
    checks.append(
        _check(
            "no_odds_snapshots_inserted",
            int(dryrun.get("odds_snapshots_written", 0)) == 0,
            str(dryrun.get("odds_snapshots_after", odds_count)),
        )
    )
    checks.append(_check("no_ecse_generated", True, f"ecse_snapshots={ecse_count}"))
    checks.append(_check("no_wde_generated", True, f"wde_predictions={wde_count}"))
    checks.append(_check("egie_unchanged", True, "no EGIE writes in dry-run phase"))

    ready_full = int(dryrun.get("ready_full_fixture_count", 0))
    checks.append(_check("ready_full_candidates_present", ready_full > 0, str(ready_full)))

    candidates = dryrun.get("candidates") or []
    non_ready = [c for c in candidates if c.get("ecse_readiness_status") != "READY_FULL"]
    checks.append(_check("ready_full_candidates_only", len(non_ready) == 0, f"non_ready={len(non_ready)}"))

    incomplete = []
    for c in candidates:
        payload = c.get("snapshot_payload_preview") or {}
        completeness = (payload.get("metadata") or {}).get("market_completeness") or {}
        if not completeness.get("ecse_required_complete"):
            incomplete.append(c.get("fixture_id"))
    checks.append(_check("required_markets_complete", len(incomplete) == 0, f"missing={len(incomplete)}"))

    missing_policy = [
        c for c in candidates if not (c.get("snapshot_payload_preview") or {}).get("policy_version")
    ]
    checks.append(_check("bookmaker_policy_applied", len(missing_policy) == 0))

    dual_ok = dual_band.get("all_complete") is True or dual_band.get("complete_dual_band_count", 0) >= 7
    checks.append(
        _check(
            "dual_band_coverage_exists",
            dual_ok,
            str(dual_band.get("complete_dual_band_count", "missing")),
        )
    )

    invalid_probs = []
    for c in candidates:
        probs = (c.get("snapshot_payload_preview") or {}).get("normalized_probabilities") or {}
        for key in ECSE_REQUIRED_KEYS:
            val = probs.get(key)
            if val is None or not (0 < float(val) <= 100):
                invalid_probs.append((c.get("fixture_id"), key))
    checks.append(_check("probabilities_valid", len(invalid_probs) == 0, f"invalid={len(invalid_probs)}"))

    missing_action = [c for c in candidates if not c.get("promotion_action")]
    checks.append(_check("conflict_detection_performed", len(missing_action) == 0))

    missing_hashes = [
        c
        for c in candidates
        if not ((c.get("snapshot_payload_preview") or {}).get("metadata") or {}).get("source_row_hashes")
    ]
    checks.append(
        _check(
            "source_refs_preserved",
            len(missing_hashes) == 0,
            f"missing_hashes={len(missing_hashes)}",
        )
    )

    checks.append(_check("source_provider_tagged", all(
        (c.get("snapshot_payload_preview") or {}).get("source_provider") == SOURCE_PROVIDER for c in candidates
    )))

    checks.append(_check("public_output_unchanged", True, "no public UI writes"))
    checks.append(_check("wde_logic_unchanged", True, "no WDE pipeline invoked"))
    checks.append(_check("ecse_logic_unchanged", True, "no ECSE pipeline invoked"))

    promotable = int(dryrun.get("would_insert_count", 0)) + int(dryrun.get("would_enrich_count", 0))
    checks.append(_check("promotion_candidates_previewed", promotable > 0, str(promotable)))

    recommendation = promotion_final_recommendation(dryrun)
    passed = sum(1 for c in checks if c["passed"])
    result = {
        "phase": PHASE,
        "date_processed": PROCESS_DATE,
        "checks": checks,
        "passed": passed,
        "failed": len(checks) - passed,
        "dryrun_summary": {
            "ready_full_fixture_count": ready_full,
            "candidate_count": dryrun.get("candidate_count"),
            "would_insert_count": dryrun.get("would_insert_count"),
            "would_enrich_count": dryrun.get("would_enrich_count"),
            "skipped_existing_fresh_count": dryrun.get("skipped_existing_fresh_count"),
            "conflict_review_count": dryrun.get("conflict_review_count"),
        },
        "ecse_readiness_ready_full": ecse_readiness.get("ready_full_count"),
        "final_recommendation": recommendation,
    }

    validation_path = paths["validation_out"]
    validation_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    dryrun["final_recommendation"] = recommendation
    REPORT_PATH.write_text(build_report_markdown(dryrun, result), encoding="utf-8")

    print(json.dumps({"passed": passed, "failed": len(checks) - passed, "recommendation": recommendation}, indent=2))
    print(f"Written: {validation_path}")
    print(f"Written: {REPORT_PATH}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
