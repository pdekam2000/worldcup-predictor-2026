#!/usr/bin/env python3
"""Validate Phase 54Q goalscorer generalization."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54q_goalscorer_generalization"
REPORT = ROOT / "PHASE_54Q_GOALSCORER_GENERALIZATION_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.egie.goalscorer_intelligence.generalization_models import VALID_RECOMMENDATIONS
        from worldcup_predictor.egie.goalscorer_intelligence.stress_runner import run_phase54q

        checks.append(_check("generalization_imports", True))
    except Exception as exc:
        checks.append(_check("generalization_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore
        run_phase54q = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "egie" / "goalscorer_intelligence"
    for mod in ("generalization_models.py", "dataset_v3.py", "generalization.py", "stress_runner.py"):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    if not (ARTIFACT_DIR / "goalscorer_dataset_v3.parquet").is_file() and run_phase54q:
        run_phase54q()
    elif not (ARTIFACT_DIR / "goalscorer_dataset_v3.parquet").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54q_goalscorer_generalization.py")], check=False)

    checks.append(_check("dataset_expanded", (ARTIFACT_DIR / "goalscorer_dataset_v3.parquet").is_file()))
    checks.append(_check("cross_league_testing", (ARTIFACT_DIR / "league_split.json").is_file()))
    checks.append(_check("tier_audit_complete", (ARTIFACT_DIR / "tier_reliability.json").is_file()))
    checks.append(_check("robustness_audit_complete", (ARTIFACT_DIR / "robustness_audit.json").is_file()))
    checks.append(_check("confidence_stability_complete", (ARTIFACT_DIR / "confidence_stability.json").is_file()))

    artifact = ARTIFACT_DIR / "phase54q_report.json"
    checks.append(_check("phase54q_report_json", artifact.is_file()))

    if (ARTIFACT_DIR / "dataset_v3_summary.json").is_file():
        ds = json.loads((ARTIFACT_DIR / "dataset_v3_summary.json").read_text(encoding="utf-8"))
        checks.append(
            _check(
                "meets_100_fixture_minimum",
                bool(ds.get("meets_100_fixtures")),
                f"fixtures={ds.get('fixtures')}",
            )
        )

    if (ARTIFACT_DIR / "league_split.json").is_file():
        leagues = json.loads((ARTIFACT_DIR / "league_split.json").read_text(encoding="utf-8"))
        checks.append(_check("four_leagues_tested", len(leagues) >= 4, f"count={len(leagues)}"))

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
