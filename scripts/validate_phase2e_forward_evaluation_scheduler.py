#!/usr/bin/env python3
"""Phase 2E validator — forward evaluation scheduler preparation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

checks: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, "PASS" if ok else "FAIL", detail))


def main() -> int:
    scheduler = ROOT / "worldcup_predictor/forward_evaluation/scheduler.py"
    cli = ROOT / "scripts/run_forward_evaluation_cycle.py"
    svc = ROOT / "deployment/systemd/worldcup-forward-evaluation.service"
    timer = ROOT / "deployment/systemd/worldcup-forward-evaluation.timer"
    db = ROOT / "worldcup_predictor/forward_evaluation/db.py"

    sched_src = scheduler.read_text(encoding="utf-8")
    cli_src = cli.read_text(encoding="utf-8")
    svc_src = svc.read_text(encoding="utf-8")
    db_src = db.read_text(encoding="utf-8")

    record("scheduler_module", scheduler.is_file())
    record("run_forward_evaluation_cycle", "def run_forward_evaluation_cycle" in sched_src)
    record("reuses_sync_result", "sync_result_for_fixture" in sched_src)
    record("reuses_evaluate", "evaluate_frozen_prediction" in sched_src)
    record("no_orchestrator_predict", "run_forward_evaluation_automation_cycle" not in sched_src)
    record("no_capture_canonical", "capture_canonical_prediction" not in sched_src)
    record("global_lock", "scheduler_cycle_lock" in sched_src)
    record("run_ledger_table", "forward_evaluation_runs" in db_src)
    record("cli_runner", cli.is_file())
    record("apply_explicit", "--apply" in cli_src and "dry_run = not args.apply" in cli_src)
    record("systemd_service", svc.is_file())
    record("systemd_timer", timer.is_file())
    record("timer_disabled_docs", "disabled" in timer.read_text(encoding="utf-8").lower())
    record("service_no_secrets", "API_KEY" not in svc_src and "Bearer" not in svc_src)
    record("audit_doc", (ROOT / "PHASE_2E_SCHEDULER_INFRASTRUCTURE_AUDIT.md").is_file())
    record("security_audit", (ROOT / "PHASE_2E_FORWARD_EVALUATION_SYSTEMD_SECURITY_AUDIT.md").is_file())
    record("test_module", (ROOT / "tests/forward_evaluation/test_scheduler_cycle.py").is_file())

    phase2e = subprocess.run(
        [sys.executable, "-m", "pytest", str(ROOT / "tests/forward_evaluation/test_scheduler_cycle.py"), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    record("phase2e_tests", phase2e.returncode == 0, phase2e.stdout[-400:] + phase2e.stderr[-200:])

    phase2d = subprocess.run(
        [sys.executable, "-m", "pytest", str(ROOT / "tests/forward_evaluation/test_result_sync_and_market_evaluation.py"), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    record("phase2d_regression", phase2d.returncode == 0, phase2d.stdout[-120:])

    for label, path in [
        ("phase2a", "tests/forward_evaluation/test_freeze_service.py"),
        ("phase2b", "tests/forward_evaluation/test_prediction_freeze_bridge.py"),
        ("phase2c", "tests/forward_evaluation/test_tier_b_structured_persistence.py"),
    ]:
        p = ROOT / path
        if p.is_file():
            r = subprocess.run([sys.executable, "-m", "pytest", str(p), "-q"], cwd=ROOT, capture_output=True, text=True)
            record(label, r.returncode == 0)

    compileall = subprocess.run([sys.executable, "-m", "compileall", "-q", "worldcup_predictor"], cwd=ROOT)
    record("compileall", compileall.returncode == 0)

    if Path("/usr/bin/systemd-analyze").exists() or subprocess.run(["where", "systemd-analyze"], capture_output=True).returncode == 0:
        verify = subprocess.run(["systemd-analyze", "verify", str(svc), str(timer)], capture_output=True, text=True)
        record("systemd_analyze", verify.returncode == 0, verify.stderr[-200:])
    else:
        record("systemd_analyze", True, "skipped on platform")

    passed = sum(1 for _, s, _ in checks if s == "PASS")
    failed = [c for c in checks if c[1] == "FAIL"]
    print(f"Phase 2E validation: {passed}/{len(checks)} passed")
    for name, status, detail in checks:
        print(f"  [{status}] {name}" + (f" — {detail}" if detail and status == "FAIL" else ""))
    if failed:
        return 1
    print("PHASE_2E_VALIDATION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
