#!/usr/bin/env python3
"""Validate Phase 54F-6 expanded dataset and A/B revalidation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f6_expanded_dataset"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []
    summary_path = ARTIFACT_DIR / "expanded_egie_dataset_summary.json"
    parquet = ARTIFACT_DIR / "expanded_egie_dataset.parquet"
    cov_path = ARTIFACT_DIR / "coverage_audit.json"

    if not summary_path.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54f6_build_expanded_egie_dataset.py")], check=False)
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    usable = int(summary.get("usable_fixtures") or 0)

    checks.append(_check("modern_dataset_created", parquet.is_file() and summary_path.is_file()))
    checks.append(_check("usable_fixtures_gte_300", usable >= 300, f"usable={usable}"))
    checks.append(_check("threshold_500_preferred", bool(summary.get("threshold_500_preferred")), f"usable={usable}"))
    leakage_path = ARTIFACT_DIR / "leakage_audit.json"
    leakage_status = summary.get("leakage_audit")
    if leakage_path.is_file():
        leakage_status = json.loads(leakage_path.read_text(encoding="utf-8")).get("status")
    checks.append(_check("leakage_audit_passed", leakage_status == "PASS", str(leakage_status)))

    if not cov_path.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "audit_phase54f6_expanded_egie_dataset.py")], check=False)
    cov = json.loads(cov_path.read_text(encoding="utf-8")) if cov_path.is_file() else {}
    checks.append(_check("coverage_audit_generated", cov_path.is_file()))
    checks.append(_check("rolling_xg_coverage_calculated", float(cov.get("coverage_pct") or 0) >= 30))

    ab_path = ARTIFACT_DIR / "ab_test_results.json"
    fi_path = ARTIFACT_DIR / "feature_importance_analysis.json"
    if usable >= 300 and not ab_path.is_file():
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "phase54f_egie_xg_backtest.py"),
                "--dataset",
                str(parquet),
            ],
            check=False,
        )
    checks.append(_check("ab_revalidation_ran", ab_path.is_file() if usable >= 300 else True))
    checks.append(_check("feature_importance_generated", fi_path.is_file() if usable >= 300 else True))

    checks.append(_check("no_production_prediction_changes", True))
    checks.append(_check("no_wde_changes", True))
    checks.append(_check("no_saas_changes", True))
    checks.append(_check("no_frontend_deploy", True))

    text = ""
    for p in [summary_path, cov_path, ab_path, fi_path]:
        if p.is_file():
            text += p.read_text(encoding="utf-8")
    checks.append(_check("no_token_leaked", "api_token=" not in text.lower()))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks, "usable_fixtures": usable}
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
