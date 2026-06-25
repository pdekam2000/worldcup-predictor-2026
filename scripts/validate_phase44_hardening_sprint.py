#!/usr/bin/env python3
"""Phase 44 hardening sprint — combined validation."""

from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _run(script: str) -> tuple[int, str]:
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / script)],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    suites = [
        ("44B_silent_failure", "validate_phase44b_silent_failure.py"),
        ("44C_billing_checkout", "validate_phase44c_billing_checkout.py"),
        ("44A_auto_evaluation", "validate_phase44a_auto_evaluation.py"),
        ("42D_global_archive", "validate_phase42d_global_archive_best_tips.py"),
    ]
    for label, script in suites:
        code, out = _run(script)
        record(label, code == 0, f"exit={code}")
        if code != 0:
            print(out[-800:])

    root = Path(__file__).resolve().parents[1]
    record("storage_contract_doc", (root / "STORAGE_CONTRACT.md").is_file())

    # Engine / WDE unchanged markers
    wde = (root / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record("wde_unchanged_marker", "log_enrichment_failure" not in wde)

    scoring = (root / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    record("scoring_engine_no_44b_logger", "log_enrichment_failure" not in scoring)

    perf = (root / "worldcup_predictor/api/performance_center.py").read_text(encoding="utf-8")
    record("best_tips_unchanged", "0.45 * hist_acc" in perf)

    eval_job = (root / "worldcup_predictor/automation/worldcup_background/result_evaluation_job.py").read_text(encoding="utf-8")
    record("auto_eval_unchanged", "stored_first" in eval_job and "skip_unchanged" in eval_job)

    out = root / "artifacts/phase44_hardening_sprint_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for _, ok, _ in checks if ok)
    out.write_text(json.dumps({
        "phase": "44_hardening",
        "passed": passed,
        "total": len(checks),
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }, indent=2), encoding="utf-8")

    print(f"\nPhase 44 hardening sprint: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
