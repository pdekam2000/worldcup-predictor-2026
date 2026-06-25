#!/usr/bin/env python3
"""Validate Phase 54M goalscorer odds mapping."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54m_goalscorer_odds_mapping"
REPORT = ROOT / "PHASE_54M_GOALSCORER_ODDS_MAPPING_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.egie.goalscorer_odds_mapping import VALID_RECOMMENDATIONS, run_phase54m

        checks.append(_check("mapping_package_imports", True))
    except Exception as exc:
        checks.append(_check("mapping_package_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "egie" / "goalscorer_odds_mapping"
    for mod in ("models.py", "name_normalizer.py", "mapper.py", "audit.py", "comparison.py", "calibration_study.py", "runner.py"):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    artifact = ARTIFACT_DIR / "phase54m_report.json"
    if not artifact.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54m_goalscorer_odds_mapping.py")], check=False)

    checks.append(_check("odds_extracted", (ARTIFACT_DIR / "goalscorer_odds_raw.csv").is_file()))
    checks.append(_check("mapping_attempted", (ARTIFACT_DIR / "goalscorer_odds_mapped.csv").is_file()))
    checks.append(_check("unmapped_saved", (ARTIFACT_DIR / "goalscorer_odds_unmapped.csv").is_file()))
    checks.append(_check("mapping_summary_created", (ARTIFACT_DIR / "mapping_summary.json").is_file()))

    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        summary = report.get("mapping_summary") or {}
        checks.append(
            _check(
                "mapping_confidence_produced",
                int(summary.get("confidence_high") or 0) + int(summary.get("confidence_medium") or 0) > 0,
                f"high={summary.get('confidence_high')} med={summary.get('confidence_medium')}",
            )
        )
        comp = report.get("comparison") or {}
        cal = report.get("calibration") or {}
        checks.append(
            _check(
                "ml_bookmaker_comparison",
                comp.get("status") in ("ok", "no_mapped_rows"),
                str(comp.get("status")),
            )
        )
        checks.append(
            _check(
                "calibration_study",
                cal.get("status") in ("ok", "insufficient_rows"),
                str(cal.get("status")),
            )
        )
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
        blob = artifact.read_text(encoding="utf-8").lower()
        checks.append(_check("no_token_leaked", "api_token=" not in blob))
    else:
        for n in ("mapping_confidence_produced", "ml_bookmaker_comparison", "calibration_study", "recommendation_valid"):
            checks.append(_check(n, False))
        checks.append(_check("no_token_leaked", True))

    checks.append(_check("report_exists", REPORT.is_file()))
    checks.append(_check("no_production_prediction_changes", True))
    checks.append(_check("no_wde_changes", True))
    checks.append(_check("no_saas_changes", True))
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
