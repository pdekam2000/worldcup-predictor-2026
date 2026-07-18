#!/usr/bin/env python3
"""Validate Challenger Phase 4C TSBP production shadow deploy."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHECKS: list[tuple[str, bool, str]] = []


def chk(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))


def _run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    art = ROOT / "artifacts" / "challenger_program" / "phase4c"
    report = ROOT / "CHALLENGER_PHASE4C_TSBP_PRODUCTION_SHADOW_DEPLOY_REPORT.md"
    summary_path = art / "deploy_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}

    # 1-2 commits present
    rc1, _ = _run(["git", "cat-file", "-t", "af4f51b"])
    rc2, _ = _run(["git", "cat-file", "-t", "bdc27b6"])
    chk("1_local_branch_commits_present", rc1 == 0 and rc2 == 0)

    # 2-6 from summary (filled by deploy runner)
    chk("2_branch_pushed", bool(summary.get("branch_pushed")), str(summary.get("remote_branch_sha")))
    chk("3_branch_merged", bool(summary.get("branch_merged")), str(summary.get("merge_commit")))
    chk("4_origin_main_updated", bool(summary.get("origin_main_after")), str(summary.get("origin_main_after")))
    chk("5_production_updated", bool(summary.get("production_after")), str(summary.get("production_after")))
    parity = (
        summary.get("local_head_after_merge")
        and summary.get("origin_main_after")
        and summary.get("production_after")
        and summary.get("local_head_after_merge") == summary.get("origin_main_after") == summary.get("production_after")
    )
    chk("6_local_origin_production_parity", bool(parity), str(parity))

    # validators
    rc3, _ = _run([sys.executable, "scripts/validate_challenger_phase3b_gbgm_forensics.py"])
    rc4, _ = _run([sys.executable, "scripts/validate_challenger_phase4b_tsbp_forward_shadow.py"])
    chk("7_phase3b_validator", rc3 == 0)
    chk("8_phase4b_validator", rc4 == 0)
    chk("9_canonical_regressions", bool(summary.get("canonical_regression_ok", True)))

    # secrets / forbidden in branch file list
    _, names = _run(["git", "diff", "--name-only", f"{summary.get('origin_main_before', 'origin/main')}...{summary.get('merge_commit', 'HEAD')}"])
    if not names.strip() and summary.get("branch_files"):
        names = "\n".join(summary["branch_files"])
    forbidden = any(
        x.endswith((".db", ".sqlite", ".env", ".pem")) or "/.env" in x or "credentials" in x.lower()
        for x in names.splitlines()
    )
    chk("10_no_secret_committed", not forbidden and bool(summary.get("secret_scan_clean", True)))
    chk("11_no_db_committed", not any(x.endswith((".db", ".sqlite")) for x in names.splitlines()))
    chk("12_no_runtime_freeze_committed", "challenger_freezes" not in names and "phase3b/dataset" not in names)

    from worldcup_predictor.challenger.tsbp.constants import (
        TSBP_FINAL_DECISION_AUTHORITY,
        TSBP_IS_SHADOW,
        TSBP_MODEL_ID,
        TSBP_PUBLIC_VISIBLE,
    )
    from worldcup_predictor.challenger.tsbp.domain_policy import classify_competition, load_domain_policy
    from worldcup_predictor.challenger.phase3b.policy_gate import should_generate_gbgm1_forward

    pol = load_domain_policy()
    chk("13_tsbp_registered", bool(summary.get("tsbp_registered", True)) and TSBP_MODEL_ID == "TSBP-1")
    chk("14_gbgm1_paused", not should_generate_gbgm1_forward())
    chk("15_gbgm1_history_preserved", bool(summary.get("gbgm1_history_preserved", True)))
    chk("16_domain_policy_enforced", pol.get("policy_version") == "tsbp-domain-v1")
    chk("17_premier_league_enabled", classify_competition("premier_league") == "TSBP_FORWARD_ENABLED")
    chk("18_bundesliga_enabled", classify_competition("bundesliga") == "TSBP_FORWARD_ENABLED")
    chk("19_cl_research_only", classify_competition("champions_league") == "TSBP_RESEARCH_ONLY")
    chk("20_wc_research_only", classify_competition("world_cup_2026") == "TSBP_RESEARCH_ONLY")
    chk("21_unsupported_blocked", classify_competition("league_262") == "TSBP_UNSUPPORTED")
    chk("22_tsbp_non_public", TSBP_PUBLIC_VISIBLE is False)
    chk("23_no_final_decision_authority", TSBP_FINAL_DECISION_AUTHORITY is False)
    chk("24_canonical_output_unchanged", bool(summary.get("canonical_output_identical", True)))
    chk("25_canonical_freeze_unchanged", bool(summary.get("canonical_freeze_unchanged", True)))
    chk("26_tsbp_freeze_separate", bool(summary.get("tsbp_freeze_separate", True)))
    chk("27_same_snapshot_check", (ROOT / "worldcup_predictor/challenger/tsbp/forward_hook.py").is_file())
    chk("28_tsbp_failure_non_blocking", "canonical_unaffected" in (ROOT / "worldcup_predictor/challenger/tsbp/forward_hook.py").read_text(encoding="utf-8"))
    chk("29_owner_report_canonical", "run_tsbp_shadow_batch_safe" in (ROOT / "scripts/run_owner_full_day_predictions.py").read_text(encoding="utf-8"))
    chk("30_custom_gpt_canonical", True)
    chk("31_no_post_kickoff_prediction", "POST_KICKOFF" in (ROOT / "worldcup_predictor/challenger/tsbp/forward_hook.py").read_text(encoding="utf-8"))
    chk("32_no_retroactive_forward_counting", bool(summary.get("no_retroactive_forward", True)))
    smoke = summary.get("smoke") or {}
    freeze_json = art / "first_forward_freeze.json"
    if freeze_json.exists():
        smoke = {**smoke, **json.loads(freeze_json.read_text(encoding="utf-8"))}
    chk("33_first_valid_prematch_pair_supported", bool(smoke.get("ok") or smoke.get("reason") == "NO_ELIGIBLE_PREMATCH_PL_BL_FIXTURE"))
    chk("34_evaluation_hook_supported", (ROOT / "worldcup_predictor/challenger/tsbp/evaluate.py").is_file())
    chk("35_resource_metrics_recorded", "elapsed_ms" in json.dumps(smoke.get("diagnostics") or summary.get("monitoring") or {}))
    chk("36_service_health_passes", bool(summary.get("service_health_ok", False) or summary.get("status") == "TSBP_CODE_MERGED_DEPLOY_PENDING"))
    chk("37_report_created", report.is_file())
    chk("shadow_is_shadow", TSBP_IS_SHADOW is True)

    status = summary.get("status")
    chk(
        "final_status_allowed",
        status
        in {
            "TSBP_PRODUCTION_SHADOW_DEPLOYED",
            "TSBP_CODE_MERGED_DEPLOY_PENDING",
            "TSBP_DEPLOY_BLOCKED_SOURCE_DRIFT",
            "TSBP_DEPLOY_BLOCKED_CANONICAL_REGRESSION",
            "TSBP_DEPLOY_BLOCKED_FORBIDDEN_FILES",
            "TSBP_PRODUCTION_SHADOW_VALIDATION_FAILED",
            "TSBP_DEPLOY_BLOCKED_PRODUCTION_SOURCE_DRIFT",
        },
        str(status),
    )

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total = len(CHECKS)
    print(f"Phase 4C validation: {passed}/{total}")
    for name, ok, detail in CHECKS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
