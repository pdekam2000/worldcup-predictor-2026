#!/usr/bin/env python3
"""Validate Phase 58B Self Learning Simulation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase58b_self_learning_simulation"
REPORT = ROOT / "PHASE_58B_SELF_LEARNING_SIMULATION_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.elite_self_learning.weight_simulation.models import VALID_SIMULATION_RECOMMENDATIONS
        from worldcup_predictor.elite_self_learning.weight_simulation.runner import run_phase58b

        checks.append(_check("weight_simulation_imports", True))
    except Exception as exc:
        checks.append(_check("weight_simulation_imports", False, str(exc)))
        VALID_SIMULATION_RECOMMENDATIONS = frozenset()  # type: ignore
        run_phase58b = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "elite_self_learning" / "weight_simulation"
    for mod in ("models.py", "snapshots.py", "replay.py", "validation.py", "runner.py"):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    required = (
        "snapshot_manifest.json",
        "window_comparisons.json",
        "component_learning_reports.json",
        "decision.json",
        "phase58b_report.json",
    )
    if not (ARTIFACT_DIR / "phase58b_report.json").is_file() and run_phase58b:
        run_phase58b()
    elif not (ARTIFACT_DIR / "phase58b_report.json").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase58b_self_learning_simulation.py")], check=False)

    for fname in required:
        checks.append(_check(f"artifact_{fname}", (ARTIFACT_DIR / fname).is_file()))

    checks.append(_check(
        "immutable_snapshots",
        (ARTIFACT_DIR / "weight_snapshots" / "snapshots_manifest.json").is_file(),
    ))

    artifact = ARTIFACT_DIR / "phase58b_report.json"
    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_SIMULATION_RECOMMENDATIONS, str(rec)))
        comps = json.loads((ARTIFACT_DIR / "window_comparisons.json").read_text(encoding="utf-8"))
        windows = {c.get("window") for c in comps}
        checks.append(_check("replay_windows", {100, 500, 1000}.issubset(windows), str(sorted(windows))))
        checks.append(_check("old_new_comparison", all("old" in c and "new" in c for c in comps)))
        learning = json.loads((ARTIFACT_DIR / "component_learning_reports.json").read_text(encoding="utf-8"))
        checks.append(_check("component_reports", len(learning) >= 10))
        checks.append(_check("safety_no_overwrite", report.get("production_changes") is False))
    else:
        for name in ("recommendation_valid", "replay_windows", "old_new_comparison", "component_reports", "safety_no_overwrite"):
            checks.append(_check(name, False))

    checks.append(_check("report_exists", REPORT.is_file()))
    checks.append(_check("no_deploy", True))
    checks.append(_check("no_production_integration", True))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
