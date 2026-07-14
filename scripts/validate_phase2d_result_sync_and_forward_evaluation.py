#!/usr/bin/env python3
"""Phase 2D validator — controlled result sync and forward market evaluation."""

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
    modules = {
        "result_record": ROOT / "worldcup_predictor/forward_evaluation/result_record.py",
        "result_sync": ROOT / "worldcup_predictor/forward_evaluation/result_sync_service.py",
        "freeze_integrity": ROOT / "worldcup_predictor/forward_evaluation/freeze_integrity.py",
        "evaluation_service": ROOT / "worldcup_predictor/forward_evaluation/evaluation_service.py",
        "evaluate": ROOT / "worldcup_predictor/forward_evaluation/evaluate.py",
        "db": ROOT / "worldcup_predictor/forward_evaluation/db.py",
    }
    for name, path in modules.items():
        record(f"module_{name}", path.is_file())

    sync_src = modules["result_sync"].read_text(encoding="utf-8")
    eval_src = modules["evaluate"].read_text(encoding="utf-8")
    db_src = modules["db"].read_text(encoding="utf-8")
    integrity_src = modules["freeze_integrity"].read_text(encoding="utf-8")

    record("sync_result_for_fixture", "def sync_result_for_fixture" in sync_src)
    record("evaluate_frozen_prediction_facade", "def evaluate_frozen_prediction" in modules["evaluation_service"].read_text(encoding="utf-8"))
    record("not_evaluated_unavailable", "NOT_EVALUATED_UNAVAILABLE" in eval_src)
    record("phase2d_migrations", "_PHASE2D_MIGRATIONS" in db_src)
    record("freeze_integrity_gate", "verify_freeze_integrity" in integrity_src)
    record("no_wde_formula_change", "def compute_wde" not in sync_src)
    record("no_ecse_recompute_in_eval", "run_ecse" not in eval_src and "ecse_live" not in eval_src)
    record("regulation_only_policy", "regulation_score_for_evaluation" in sync_src)
    record("dry_run_script", (ROOT / "scripts/dry_run_phase2d_forward_evaluation.py").is_file())
    record("audit_doc", (ROOT / "PHASE_2D_RESULT_AND_EVALUATION_CURRENT_STATE_AUDIT.md").is_file())
    record("schema_design_doc", (ROOT / "PHASE_2D_FORWARD_EVALUATION_SCHEMA_DESIGN.md").is_file())
    record("test_module", (ROOT / "tests/forward_evaluation/test_result_sync_and_market_evaluation.py").is_file())

    phase2d = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(ROOT / "tests/forward_evaluation/test_result_sync_and_market_evaluation.py"),
            "-q",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    record("phase2d_unit_tests", phase2d.returncode == 0, phase2d.stdout[-400:] + phase2d.stderr[-200:])

    for label, path in [
        ("phase2a_freeze", "tests/forward_evaluation/test_freeze_service.py"),
        ("phase2b_bridge", "tests/forward_evaluation/test_prediction_freeze_bridge.py"),
        ("phase2c_tier_b", "tests/forward_evaluation/test_tier_b_structured_persistence.py"),
    ]:
        p = ROOT / path
        if p.is_file():
            r = subprocess.run([sys.executable, "-m", "pytest", str(p), "-q"], cwd=ROOT, capture_output=True, text=True)
            record(label, r.returncode == 0, r.stdout[-120:])

    compileall = subprocess.run([sys.executable, "-m", "compileall", "-q", "worldcup_predictor"], cwd=ROOT)
    record("compileall", compileall.returncode == 0)

    passed = sum(1 for _, s, _ in checks if s == "PASS")
    failed = [c for c in checks if c[1] == "FAIL"]
    print(f"Phase 2D validation: {passed}/{len(checks)} passed")
    for name, status, detail in checks:
        print(f"  [{status}] {name}" + (f" — {detail}" if detail and status == "FAIL" else ""))
    if failed:
        return 1
    print("PHASE_2D_VALIDATION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
