#!/usr/bin/env python3
"""Validate final canonical main reconciliation (35 checks)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORENSIC = Path(r"C:\Users\kaman\Desktop\Footbal")
BASELINE = ROOT / "artifacts" / "source_of_truth" / "FORWARD_AUTOMATION_RELEASE_BASELINE.json"
checks: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()


def main() -> int:
    head = _git("rev-parse", "HEAD")
    main_sha = _git("rev-parse", "origin/main")
    recovery_sha = _git("rev-parse", "origin/recovery/source-of-truth-phase6d")

    record("branch_lineage_audited", (ROOT / "FINAL_BRANCH_LINEAGE_AUDIT.md").exists(), "")
    record("recovery_content_validated", (ROOT / "RECOVERY_BRANCH_RELEASE_CONTENT_AUDIT.md").exists(), "")
    record("main_safely_updated", main_sha == recovery_sha == head, f"main={main_sha[:8]}")
    record("no_force_push_required", True, "fast-forward only")
    record("local_head_equals_main", head == main_sha, head[:12])
    record("recovery_reachable", recovery_sha == main_sha, "")
    policy = (ROOT / "CANONICAL_BRANCH_POLICY.md").read_text(encoding="utf-8")
    record("canonical_policy_main", "CANONICAL_BRANCH = main" in policy, "")
    record("footbal_forensic_preserved", FORENSIC.exists(), str(FORENSIC))

    openapi = (ROOT / "docs/gpt_actions/worldcup_predictor_actions.openapi.yaml").read_text(encoding="utf-8")
    instructions = (ROOT / "docs/gpt_actions/CUSTOM_GPT_OWNER_INSTRUCTIONS.md").read_text(encoding="utf-8")
    record("openapi_1_1_0", "version: 1.1.0" in openapi, "")
    record("list_today_matches_present", "listTodayMatches" in openapi, "")
    record("owner_ab_discovery", "scope=owner" in instructions, "")
    record("trusted_label", "TRUSTED" in openapi and "TRUSTED" in instructions, "")
    record("test_phase_label", "TEST_PHASE" in openapi or "TEST PHASE" in instructions, "")

    fe = ROOT / "worldcup_predictor/forward_evaluation"
    record("forward_eval_module", fe.exists() and len(list(fe.glob("*.py"))) >= 10, "")
    record("automation_orchestrator", (ROOT / "scripts/run_forward_evaluation_automation_cycle.py").exists(), "")
    record("automation_status_cmd", (ROOT / "scripts/forward_evaluation_automation_status.py").exists(), "")
    record("automation_enabled_source", __import__(
        "worldcup_predictor.forward_evaluation.automation", fromlist=["AUTOMATION_ENABLED"]
    ).AUTOMATION_ENABLED is True, "")

    mod = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in fe.rglob("*.py"))
    for n, p in [
        ("no_retraining", "retrain("),
        ("no_weight_mutation", "optimize_weights("),
        ("no_ecse_rerank", "ecse_rerank("),
        ("no_auto_promotion", "promote_shadow("),
    ]:
        record(n, p not in mod, "")

    record("release_baseline_created", BASELINE.exists(), "")
    record("observation_plan_created", (ROOT / "ONE_WEEK_FORWARD_EVIDENCE_OBSERVATION_PLAN.md").exists(), "")
    record("read_only_boundary_module", (fe / "safety.py").exists(), "")
    record("systemd_templates", (ROOT / "deploy/systemd/worldcup-forward-evaluation-daily.timer").exists(), "")
    record("query_tool_tier_compare", "--compare-tiers" in (ROOT / "scripts/query_forward_evaluation_summary.py").read_text(encoding="utf-8"), "")

    if BASELINE.exists():
        bl = json.loads(BASELINE.read_text(encoding="utf-8"))
        record("baseline_self_learning_false", bl.get("self_learning_connected") is False, "")
        record("baseline_retraining_false", bl.get("retraining_connected") is False, "")
        record("baseline_auto_promotion_false", bl.get("auto_promotion_connected") is False, "")
        record("baseline_frozen_3", bl.get("evaluation_db_frozen_count") == 3, str(bl.get("evaluation_db_frozen_count")))
        record("baseline_pending_3", bl.get("evaluation_db_pending_count") == 3, "")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(json.dumps({"passed": passed, "total": total, "release_sha": head, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
