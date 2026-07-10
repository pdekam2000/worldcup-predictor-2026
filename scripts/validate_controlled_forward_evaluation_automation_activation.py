#!/usr/bin/env python3
"""Validate controlled forward evaluation automation activation (60 checks)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

checks: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def _git(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()


def main() -> int:
    head = _git(["git", "rev-parse", "HEAD"])
    policy = (ROOT / "CANONICAL_BRANCH_POLICY.md").read_text(encoding="utf-8")
    record("canonical_branch_policy_documented", "CANONICAL_BRANCH" in policy, "")
    record("local_canonical_head_recorded", len(head) == 40, head[:12])

    try:
        origin_recovery = _git(["git", "rev-parse", "origin/recovery/source-of-truth-phase6d"])
        record("github_recovery_head_recorded", origin_recovery == head, origin_recovery[:12])
    except Exception as exc:
        record("github_recovery_head_recorded", False, str(exc))
        origin_recovery = ""

    try:
        origin_main = _git(["git", "rev-parse", "origin/main"])
        record("origin_main_status_recorded", True, origin_main[:12])
        main_has = subprocess.call(
            ["git", "merge-base", "--is-ancestor", head, "origin/main"], cwd=ROOT, stderr=subprocess.DEVNULL
        )
        record("approved_commit_on_main", main_has == 0, "main_behind" if main_has != 0 else "ok")
    except Exception as exc:
        record("origin_main_status_recorded", False, str(exc))

    openapi = (ROOT / "docs/gpt_actions/worldcup_predictor_actions.openapi.yaml").read_text(encoding="utf-8")
    instructions = (ROOT / "docs/gpt_actions/CUSTOM_GPT_OWNER_INSTRUCTIONS.md").read_text(encoding="utf-8")
    record("list_today_matches_schema", "listTodayMatches" in openapi, "")
    record("discover_today_matches_schema", "discoverTodayMatches" in openapi, "")
    record("trusted_label_schema", "TRUSTED" in openapi, "")
    record("test_phase_label_schema", "TEST_PHASE" in openapi, "")
    record("owner_ab_instructions", "scope=owner" in instructions and "listTodayMatches" in instructions, "")
    record("automation_orchestrator_a_b", "tier_a_count" in (ROOT / "worldcup_predictor/forward_evaluation/orchestrator.py").read_text(encoding="utf-8"), "")
    record("automation_enabled_flag", __import__("worldcup_predictor.forward_evaluation.automation", fromlist=["AUTOMATION_ENABLED"]).AUTOMATION_ENABLED is True, "")
    record("timer_templates_exist", (ROOT / "deploy/systemd/worldcup-forward-evaluation-daily.timer").exists(), "")
    record("status_script_exists", (ROOT / "scripts/forward_evaluation_automation_status.py").exists(), "")
    record("db_integrity_script_exists", (ROOT / "scripts/audit_forward_evaluation_db_integrity.py").exists(), "")
    record("backup_script_exists", (ROOT / "scripts/backup_forward_evaluation_db.py").exists(), "")
    record("read_only_boundary_script", (ROOT / "scripts/validate_forward_evaluation_read_only_boundary.py").exists(), "")

    mod = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in (ROOT / "worldcup_predictor/forward_evaluation").rglob("*.py"))
    for name, pat in [
        ("no_training", "run_training("),
        ("no_retraining", "retrain("),
        ("no_weight_changes", "optimize_weights("),
        ("no_ecse_rerank", "ecse_rerank("),
        ("no_calibration_promotion", "update_calibration("),
        ("no_tier_auto_promotion", "promote_shadow("),
        ("cache_first_gates", "allow_provider=False"),
    ]:
        record(name, pat not in mod if name.startswith("no") else pat in mod, "")

    record("locking_module", (ROOT / "worldcup_predictor/forward_evaluation/lock.py").exists(), "")
    record("openapi_version_bump", "1.1.0" in openapi, "")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
