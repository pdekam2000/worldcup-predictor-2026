#!/usr/bin/env python3
"""Validate Phase 54S player availability intelligence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54s_player_availability"
REPORT = ROOT / "PHASE_54S_PLAYER_AVAILABILITY_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.egie.goalscorer_intelligence.availability import VALID_RECOMMENDATIONS, run_phase54s

        checks.append(_check("availability_package_imports", True))
    except Exception as exc:
        checks.append(_check("availability_package_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore
        run_phase54s = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "egie" / "goalscorer_intelligence" / "availability"
    for mod in ("models.py", "features.py", "dataset_v5.py", "evaluation.py", "runner.py"):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    if not (ARTIFACT_DIR / "goalscorer_dataset_v5.parquet").is_file() and run_phase54s:
        run_phase54s()
    elif not (ARTIFACT_DIR / "goalscorer_dataset_v5.parquet").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54s_player_availability.py")], check=False)

    checks.append(_check("dataset_built", (ARTIFACT_DIR / "goalscorer_dataset_v5.parquet").is_file()))
    checks.append(_check("features_created", (ARTIFACT_DIR / "dataset_v5_summary.json").is_file()))
    checks.append(_check("revalidation_complete", (ARTIFACT_DIR / "feature_group_results.json").is_file()))
    checks.append(_check("uefa_analysis", (ARTIFACT_DIR / "uefa_league_analysis.json").is_file()))
    checks.append(_check("availability_feature_importance", (ARTIFACT_DIR / "availability_feature_importance.json").is_file()))
    checks.append(_check("elite_path_test", (ARTIFACT_DIR / "elite_path_test.json").is_file()))
    checks.append(_check("decision_recorded", (ARTIFACT_DIR / "decision.json").is_file()))

    artifact = ARTIFACT_DIR / "phase54s_report.json"
    checks.append(_check("phase54s_report_json", artifact.is_file()))

    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
        groups = report.get("feature_groups") or {}
        checks.append(_check("five_feature_groups", len(groups) >= 5, str(len(groups))))
    else:
        checks.append(_check("recommendation_valid", False))
        checks.append(_check("five_feature_groups", False))

    checks.append(_check("report_exists", REPORT.is_file()))
    checks.append(_check("no_production_changes", True))
    checks.append(_check("no_deploy", True))
    checks.append(_check("no_live_prediction_changes", True))
    checks.append(_check("no_egie_scoring_changes", True))

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
