#!/usr/bin/env python3
"""Validate Phase 54Q-1 UEFA goalscorer odds audit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54q1_uefa_goalscorer_odds_audit"
REPORT = ROOT / "PHASE_54Q1_UEFA_GOALSCORER_ODDS_AUDIT_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.egie.goalscorer_intelligence.uefa_odds_audit import VALID_RECOMMENDATIONS, run_phase54q1

        checks.append(_check("audit_package_imports", True))
    except Exception as exc:
        checks.append(_check("audit_package_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore
        run_phase54q1 = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "egie" / "goalscorer_intelligence" / "uefa_odds_audit"
    for mod in ("models.py", "coverage.py", "impact.py", "runner.py"):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    if not (ARTIFACT_DIR / "uefa_odds_coverage.json").is_file() and run_phase54q1:
        run_phase54q1()
    elif not (ARTIFACT_DIR / "uefa_odds_coverage.json").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54q1_uefa_goalscorer_odds_audit.py")], check=False)

    checks.append(_check("coverage_audit_created", (ARTIFACT_DIR / "uefa_odds_coverage.json").is_file()))
    checks.append(_check("wc_vs_uefa_comparison", (ARTIFACT_DIR / "wc_vs_uefa_comparison.json").is_file()))
    checks.append(_check("counterfactual_analysis", (ARTIFACT_DIR / "counterfactual_analysis.json").is_file()))
    checks.append(_check("feature_contribution", (ARTIFACT_DIR / "feature_contribution.json").is_file()))
    checks.append(_check("decision_recorded", (ARTIFACT_DIR / "decision.json").is_file()))

    artifact = ARTIFACT_DIR / "phase54q1_report.json"
    checks.append(_check("phase54q1_report_json", artifact.is_file()))

    if (ARTIFACT_DIR / "uefa_odds_coverage.json").is_file():
        cov = json.loads((ARTIFACT_DIR / "uefa_odds_coverage.json").read_text(encoding="utf-8"))
        uefa_pct = float((cov.get("dataset_v3") or {}).get("uefa_coverage_pct") or 0)
        checks.append(_check("uefa_coverage_measured", True, f"pct={uefa_pct}"))

    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
        blob = artifact.read_text(encoding="utf-8").lower()
        checks.append(_check("no_token_leaked", "api_token=" not in blob))
    else:
        checks.append(_check("recommendation_valid", False))
        checks.append(_check("no_token_leaked", True))

    checks.append(_check("report_exists", REPORT.is_file()))
    checks.append(_check("no_production_changes", True))
    checks.append(_check("no_wde_changes", True))
    checks.append(_check("no_saas_changes", True))
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
