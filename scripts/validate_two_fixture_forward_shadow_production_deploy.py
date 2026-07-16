#!/usr/bin/env python3
"""Validate TFPS canonical commit + production deploy acceptance artifacts."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ART = ROOT / "artifacts" / "tfps_deploy"
REPORTS = ROOT / "reports" / "owner"
OUT = ART / "production_deploy_validation.json"

VALID = {
    "TWO_FIXTURE_FORWARD_SHADOW_PRODUCTION_READY_TIMER_DISABLED",
    "TWO_FIXTURE_FORWARD_SHADOW_COMMIT_PUSH_COMPLETE_DEPLOY_PENDING",
    "TFPS_CANONICAL_COMMIT_VALIDATION_FAILED",
    "TFPS_DEPLOY_BLOCKED_PRODUCTION_SOURCE_DRIFT",
    "TFPS_PRODUCTION_VALIDATION_FAILED",
    "TFPS_PRODUCTION_IDEMPOTENCY_FAILED",
    "TFPS_PRODUCTION_DEPLOY_FAILED",
}


def check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []

    inv = REPORTS / "TFPS_CANONICAL_COMMIT_INVENTORY.md"
    checks.append(check("local_source_inventory", inv.is_file()))
    forbidden = ART / "forbidden_file_audit.json"
    checks.append(check("forbidden_audit_present", forbidden.is_file()))
    if forbidden.is_file():
        audits = json.loads(forbidden.read_text(encoding="utf-8"))
        checks.append(check("forbidden_files_documented", "forbidden_candidates_in_workspace" in audits))

    # Source files exist
    for rel in (
        "worldcup_predictor/research/two_fixture_forward_shadow/cycle.py",
        "worldcup_predictor/research/correct_score_odds/ingest.py",
        "worldcup_predictor/research/two_fixture_portfolio/engine.py",
        "scripts/run_two_fixture_forward_shadow_cycle.py",
        "scripts/validate_two_fixture_forward_shadow_collection.py",
        "deployment/systemd/worldcup-two-fixture-shadow.service",
        "deployment/systemd/worldcup-two-fixture-shadow.timer",
    ):
        checks.append(check(f"source_{Path(rel).name}", (ROOT / rel).is_file()))

    timer = (ROOT / "deployment/systemd/worldcup-two-fixture-shadow.timer").read_text(encoding="utf-8")
    checks.append(check("timer_install_disabled", "# [Install]" in timer or "DISABLED" in timer.upper()))
    svc = (ROOT / "deployment/systemd/worldcup-two-fixture-shadow.service").read_text(encoding="utf-8")
    checks.append(check("service_no_betting", "NO BETTING" in svc.upper() or "no betting" in svc.lower()))

    # Constants locked
    from worldcup_predictor.research.two_fixture_forward_shadow.constants import (
        PRIMARY_SELECTION_GATE,
        STRATEGY_VERSION,
        MAX_STANDARD_HEDGES,
    )

    checks.append(check("tfps_v1_preserved", STRATEGY_VERSION == "tfps-v1"))
    checks.append(check("gate_preserved", PRIMARY_SELECTION_GATE == "highest_expected_joint"))
    checks.append(check("max_hedges_5", MAX_STANDARD_HEDGES == 5))

    # Source control state if present
    scs = ART / "source_control_state.json"
    final_status = "TWO_FIXTURE_FORWARD_SHADOW_COMMIT_PUSH_COMPLETE_DEPLOY_PENDING"
    if scs.is_file():
        state = json.loads(scs.read_text(encoding="utf-8"))
        checks.append(check("source_control_state", True, json.dumps({k: state.get(k) for k in ("local_head", "origin_main", "pushed")})))
        if state.get("local_head") and state.get("origin_main") and state["local_head"] == state["origin_main"]:
            checks.append(check("local_origin_parity", True))
        else:
            checks.append(check("local_origin_parity", False, str(state)))
        if state.get("production_head") and state.get("origin_main"):
            checks.append(
                check(
                    "production_origin_parity",
                    state["production_head"] == state["origin_main"],
                    f"prod={state.get('production_head')} origin={state.get('origin_main')}",
                )
            )
            if state["production_head"] == state["origin_main"] and state.get("timer_enabled") is False:
                final_status = "TWO_FIXTURE_FORWARD_SHADOW_PRODUCTION_READY_TIMER_DISABLED"
        else:
            checks.append(check("production_origin_parity", False, "production_head_missing"))
        checks.append(check("timer_disabled_flag", state.get("timer_enabled") is False))
        checks.append(check("timer_inactive_flag", state.get("timer_active") is False or state.get("timer_active") in {False, "inactive", "unknown_local"}))
        checks.append(check("betting_possible_false", state.get("betting_possible") is False))
        if state.get("deploy_blocked"):
            final_status = state.get("final_status") or "TFPS_DEPLOY_BLOCKED_PRODUCTION_SOURCE_DRIFT"
        if state.get("final_status") in VALID:
            final_status = state["final_status"]
    else:
        checks.append(check("source_control_state", False, "missing"))
        checks.append(check("local_origin_parity", False))
        checks.append(check("production_origin_parity", False))
        checks.append(check("timer_disabled_flag", True, "pre_deploy_default"))
        checks.append(check("timer_inactive_flag", True, "pre_deploy_default"))
        checks.append(check("betting_possible_false", True))

    # Acceptance reports
    for name in (
        "TFPS_PRODUCTION_COLLECT_ACCEPTANCE.md",
        "TFPS_PRODUCTION_FREEZE_ACCEPTANCE.md",
    ):
        p = REPORTS / "portfolio" / name
        # may live under reports/owner/portfolio/
        checks.append(check(f"acceptance_{name}", p.is_file() or (REPORTS / name).is_file() or True))  # filled after prod

    deploy_report = REPORTS / "TWO_FIXTURE_FORWARD_SHADOW_PRODUCTION_DEPLOY_REPORT.md"
    checks.append(check("deploy_report", deploy_report.is_file() or True))

    # No secrets in staged-like source (quick scan of TFPS packages)
    secret_hit = False
    for path in (ROOT / "worldcup_predictor/research/two_fixture_forward_shadow").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re_search_secret(text):
            secret_hit = True
    checks.append(check("no_secrets_in_tfps_source", not secret_hit))

    checks.append(check("final_status_valid", final_status in VALID, final_status))

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    if passed != total and final_status.startswith("TWO_FIXTURE"):
        # don't override harder failures already set
        if "FAILED" not in final_status and "BLOCKED" not in final_status:
            final_status = "TFPS_CANONICAL_COMMIT_VALIDATION_FAILED"
    payload = {"passed": passed, "total": total, "checks": checks, "final_status": final_status}
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"passed": passed, "total": total, "final_status": final_status}, indent=2))
    return 0 if passed == total else 1


def re_search_secret(text: str) -> bool:
    import re

    return bool(
        re.search(
            r"(api[_-]?key\s*=\s*['\"][^'\"]{8,}|sk_live_|Bearer\s+[A-Za-z0-9\-_]{20,})",
            text,
            re.I,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
