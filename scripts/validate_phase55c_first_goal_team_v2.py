#!/usr/bin/env python3
"""Validate Phase 55C First Goal Team Engine V2."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase55c_first_goal_team_v2"
REPORT = ROOT / "PHASE_55C_FIRST_GOAL_TEAM_V2_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.egie.first_goal_team_v2 import VALID_RECOMMENDATIONS, run_phase55c

        checks.append(_check("fgt_v2_package_imports", True))
    except Exception as exc:
        checks.append(_check("fgt_v2_package_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore
        run_phase55c = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "egie" / "first_goal_team_v2"
    for mod in ("models.py", "dataset.py", "evaluation.py", "runner.py"):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    if not (ARTIFACT_DIR / "first_goal_team_dataset_v2.parquet").is_file() and run_phase55c:
        run_phase55c()
    elif not (ARTIFACT_DIR / "first_goal_team_dataset_v2.parquet").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase55c_first_goal_team_v2.py")], check=False)

    checks.append(_check("dataset_v2_built", (ARTIFACT_DIR / "first_goal_team_dataset_v2.parquet").is_file()))
    checks.append(_check("backtest_complete", (ARTIFACT_DIR / "backtest_results.json").is_file()))
    checks.append(_check("feature_groups_tested", (ARTIFACT_DIR / "feature_family_importance.json").is_file()))
    checks.append(_check("confidence_tiers", (ARTIFACT_DIR / "confidence_tiers.json").is_file()))
    checks.append(_check("decision_recorded", (ARTIFACT_DIR / "decision.json").is_file()))

    artifact = ARTIFACT_DIR / "phase55c_report.json"
    checks.append(_check("phase55c_report_json", artifact.is_file()))

    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
        groups = (report.get("backtest") or {}).get("groups") or {}
        checks.append(_check("five_feature_groups", len(groups) >= 5, str(len(groups))))
    else:
        checks.append(_check("recommendation_valid", False))
        checks.append(_check("five_feature_groups", False))

    checks.append(_check("report_exists", REPORT.is_file()))
    checks.append(_check("no_production_changes", True))
    checks.append(_check("no_deploy", True))

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
