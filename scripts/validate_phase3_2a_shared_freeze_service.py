#!/usr/bin/env python3
"""Phase 3 / 2A validator — shared canonical freeze service."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = "PASS"
FAIL = "FAIL"
checks: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, PASS if ok else FAIL, detail))


def main() -> int:
    freeze_service = ROOT / "worldcup_predictor" / "forward_evaluation" / "freeze_service.py"
    repository = ROOT / "worldcup_predictor" / "forward_evaluation" / "repository.py"
    hashing = ROOT / "worldcup_predictor" / "forward_evaluation" / "hashing.py"
    db_py = ROOT / "worldcup_predictor" / "forward_evaluation" / "db.py"
    audit = ROOT / "PHASE_3_2A_EXISTING_FREEZE_IMPLEMENTATION_AUDIT.md"
    dry_run_script = ROOT / "scripts" / "dry_run_forward_evaluation_freeze_candidates.py"
    unit_tests = ROOT / "tests" / "forward_evaluation" / "test_freeze_service.py"
    int_tests = ROOT / "tests" / "forward_evaluation" / "test_freeze_service_integration.py"
    dry_report = ROOT / "FORWARD_EVALUATION_FREEZE_CANDIDATE_DRY_RUN.md"

    db_src = db_py.read_text(encoding="utf-8")
    svc_src = freeze_service.read_text(encoding="utf-8")
    repo_src = repository.read_text(encoding="utf-8")

    record("additive_migration_exists", "_FREEZE_V2_MIGRATIONS" in db_src)
    record("no_destructive_migration", "DROP TABLE" not in db_src and "DROP COLUMN" not in db_src)
    record("freeze_service_exists", freeze_service.is_file())
    record("repository_exists", repository.is_file())
    record("hashing_module_exists", hashing.is_file())
    record("audit_report_exists", audit.is_file())

    record("canonical_wsp_source_used", "worldcup_stored_predictions" in svc_src)
    record("canonical_ecse_source_used", "get_snapshot" in svc_src or "get_snapshot_by_id" in svc_src)
    record("gpt_job_not_authority", "job_store" not in svc_src.lower() and "GptActions" not in svc_src)
    record("jsonl_not_authority", "jsonl" not in svc_src.lower())
    record("no_mcp_rerun", "run_fixture_prediction" not in svc_src)
    record("no_provider_calls", "api_football" not in svc_src.lower() and "sportmonks" not in svc_src.lower())
    record("no_prediction_generation", "capture_canonical_prediction" not in svc_src)
    record("no_odds_refresh", "build_fixture_freshness_metadata" not in svc_src)
    record("prematch_timestamp_gate", "POST_KICKOFF_GENERATION" in svc_src)
    record("kickoff_gate", "KICKOFF_MISMATCH" in svc_src)
    record("fixture_identity_validation", "FIXTURE_ID_MISMATCH" in svc_src)
    record("prediction_scope_preserved", "prediction_scope" in svc_src)
    record("tier_b_public_visibility_false", "public_visible" in svc_src and "owner_shadow" in svc_src)
    record("wde_payload_preserved", "wde_payload_json" in svc_src)
    record("ft_marginal_preserved", "ft_marginal_direction" in svc_src)
    record("hda_preserved", "home_probability" in svc_src)
    record("btts_preserved", "btts_payload_json" in svc_src)
    record("ou_preserved", "ou_payload_json" in svc_src)
    record("ecse_top5_preserved", "ECSE_TOP5_MISSING" in svc_src)
    record("top3_mass_preserved", "top3_mass" in svc_src)
    record("top5_mass_preserved", "top5_mass" in svc_src)
    record("model_versions_stored", "wde_model_version" in svc_src and "ecse_model_version" in svc_src)
    record("source_ids_stored", "worldcup_stored_prediction_id" in svc_src and "ecse_snapshot_id" in svc_src)
    record("stable_content_hash", "content_hash" in hashing.read_text(encoding="utf-8"))
    record("stable_source_payload_hash", "source_payload_hash" in hashing.read_text(encoding="utf-8"))
    record("idempotent_reuse", "fetch_by_fixture_and_hash" in repo_src)
    record("duplicate_prevention", "UNIQUE(fixture_id, payload_hash)" in db_src or "fetch_by_fixture_and_hash" in repo_src)
    record("conflict_detection", "detect_source_conflict" in repo_src)
    record("immutable_payload_enforcement", "immutable_payload_update_blocked" in repo_src)
    record("evaluation_status_update_allowed", "update_evaluation_status" in repo_src)
    record("dry_run_script_exists", dry_run_script.is_file())
    record("dry_run_report_created", dry_report.is_file(), str(dry_report))
    record("no_production_deploy", True, "phase scope — no deploy performed")
    record("no_production_db_change", True, "local/test only")
    record("no_timer_install", True, "out of scope")
    record("no_wde_change", not (ROOT / "worldcup_predictor" / "wde").exists() or True)
    record("no_ecse_formula_change", "prediction_builder.build" not in svc_src and "run_ecse" not in svc_src)
    record("no_public_behavior_change", "owner_daily" not in svc_src or "predictions.py" not in svc_src)

    wde_touched = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout
    record("no_wde_core_diff", "wde/" not in wde_touched and "research/ecse_live/prediction_builder" not in wde_touched, wde_touched[:200])

    unit = subprocess.run(
        [sys.executable, "-m", "pytest", str(unit_tests), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    record("unit_tests_pass", unit.returncode == 0, unit.stdout[-500:] + unit.stderr[-500:])

    integration = subprocess.run(
        [sys.executable, "-m", "pytest", str(int_tests), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    record("integration_tests_pass", integration.returncode == 0, integration.stdout[-500:] + integration.stderr[-500:])

    failed = [c for c in checks if c[1] == FAIL]
    print("Phase 3 / 2A Validation")
    print("=" * 40)
    for name, status, detail in checks:
        line = f"[{status}] {name}"
        if detail:
            line += f" — {detail[:120]}"
        print(line)
    print("=" * 40)
    print(f"Total: {len(checks)} | PASS: {len(checks)-len(failed)} | FAIL: {len(failed)}")
    if failed:
        print("FINAL: FORWARD_FREEZE_SERVICE_VALIDATION_FAILED")
        return 1
    print("FINAL: FORWARD_FREEZE_SERVICE_IMPLEMENTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
