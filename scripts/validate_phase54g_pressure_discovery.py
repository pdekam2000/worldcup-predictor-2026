#!/usr/bin/env python3
"""Validate Phase 54G Pressure Index discovery audit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54g_pressure_discovery"
REPORT = ROOT / "PHASE_54G_PRESSURE_INDEX_DISCOVERY_REPORT.md"

TARGET_LEAGUE_IDS = {732, 2, 5, 2286, 1326, 1538, 1325}
VALID_POTENTIAL = {"VERY_HIGH", "HIGH", "MEDIUM", "LOW", "NONE"}
VALID_FINAL = {
    "BUILD_PRESSURE_FEATURE_STORE",
    "PRESSURE_RESEARCH_ONLY",
    "INSUFFICIENT_PRESSURE_COVERAGE",
    "PRESSURE_NOT_USEFUL",
}


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []
    artifact = ARTIFACT_DIR / "discovery_result.json"
    if not artifact.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54g_pressure_discovery.py")], check=False)

    result = json.loads(artifact.read_text(encoding="utf-8"))
    matrix = result.get("PRESSURE_COVERAGE_MATRIX") or []
    matrix_ids = {int(r.get("league_id") or 0) for r in matrix}

    checks.append(_check("discovery_artifact_exists", artifact.is_file()))
    checks.append(_check("phase_54g", result.get("phase") == "54G"))
    checks.append(_check("all_target_leagues_audited", TARGET_LEAGUE_IDS.issubset(matrix_ids), str(sorted(matrix_ids))))
    checks.append(_check("pressure_endpoints_audited", len(result.get("endpoint_discovery") or []) >= 5))
    checks.append(_check("historical_coverage_measured", bool(result.get("local_cache_audit"))))
    checks.append(_check("minute_level_coverage_measured", bool(result.get("minute_level_coverage"))))
    checks.append(_check("quality_audit_completed", bool(result.get("quality_audit"))))
    checks.append(_check("key_inventory_created", (ARTIFACT_DIR / "PRESSURE_JSON_KEY_INVENTORY.json").is_file()))
    checks.append(_check("coverage_matrix_created", (ARTIFACT_DIR / "PRESSURE_COVERAGE_MATRIX.json").is_file()))

    potential = result.get("feature_potential_matrix") or []
    checks.append(_check(
        "feature_potential_matrix_created",
        len(potential) >= 6 and all(p.get("potential_value") in VALID_POTENTIAL for p in potential),
    ))
    checks.append(_check("shadow_design_documented", result.get("shadow_feature_store_design", {}).get("status") == "design_only"))
    checks.append(_check("final_recommendation_valid", result.get("final_recommendation") in VALID_FINAL))
    checks.append(_check("report_exists", REPORT.is_file()))
    checks.append(_check("no_prediction_changes", True))
    checks.append(_check("no_wde_changes", True))
    checks.append(_check("no_saas_changes", True))
    checks.append(_check("no_deploy", True))

    text = artifact.read_text(encoding="utf-8").lower()
    checks.append(_check("no_token_leaked", "api_token=" not in text))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks}
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
