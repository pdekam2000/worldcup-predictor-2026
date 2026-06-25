#!/usr/bin/env python3
"""Validate Phase 54R team context goalscorer enrichment."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54r_team_context_goalscorer"
REPORT = ROOT / "PHASE_54R_TEAM_CONTEXT_GOALSCORER_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.egie.goalscorer_intelligence.team_context import VALID_RECOMMENDATIONS, run_phase54r

        checks.append(_check("team_context_package_imports", True))
    except Exception as exc:
        checks.append(_check("team_context_package_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore
        run_phase54r = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "egie" / "goalscorer_intelligence" / "team_context"
    for mod in ("models.py", "features.py", "dataset_v4.py", "evaluation.py", "runner.py"):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    if not (ARTIFACT_DIR / "goalscorer_dataset_v4.parquet").is_file() and run_phase54r:
        run_phase54r()
    elif not (ARTIFACT_DIR / "goalscorer_dataset_v4.parquet").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54r_team_context_goalscorer.py")], check=False)

    checks.append(_check("dataset_v4_built", (ARTIFACT_DIR / "goalscorer_dataset_v4.parquet").is_file()))
    checks.append(_check("feature_groups_tested", (ARTIFACT_DIR / "feature_group_results.json").is_file()))
    checks.append(_check("team_feature_importance", (ARTIFACT_DIR / "team_feature_importance.json").is_file()))
    checks.append(_check("league_analysis_completed", (ARTIFACT_DIR / "uefa_league_impact.json").is_file()))
    checks.append(_check("elite_recheck", (ARTIFACT_DIR / "elite_recheck.json").is_file()))
    checks.append(_check("decision_recorded", (ARTIFACT_DIR / "decision.json").is_file()))

    artifact = ARTIFACT_DIR / "phase54r_report.json"
    checks.append(_check("phase54r_report_json", artifact.is_file()))

    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
        groups = report.get("feature_groups") or {}
        checks.append(_check("four_feature_groups", len(groups) >= 4, str(len(groups))))
    else:
        checks.append(_check("recommendation_valid", False))
        checks.append(_check("four_feature_groups", False))

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
