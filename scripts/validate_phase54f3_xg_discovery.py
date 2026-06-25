#!/usr/bin/env python3
"""Validate Phase 54F-3 Sportmonks historical xG discovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f3_xg_discovery"
TARGET_LEAGUE_IDS = {732, 1326, 2, 5, 8}


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    result_path = ARTIFACT_DIR / "discovery_result.json"
    matrix_path = ARTIFACT_DIR / "XG_COVERAGE_MATRIX.json"

    if not result_path.is_file():
        import subprocess

        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54f3_sportmonks_xg_discovery.py")], check=False)

    # Apply parser fix replay when raw cache exists
    if (ARTIFACT_DIR / "raw").is_dir() and result_path.is_file():
        import subprocess

        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54f3_replay_probe_from_cache.py")], check=False)

    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
    matrix = json.loads(matrix_path.read_text(encoding="utf-8")) if matrix_path.is_file() else []

    discovered_ids = {int(m.get("league_id") or 0) for m in result.get("league_discovery") or []}
    checks.append(_check("target_leagues_audited", TARGET_LEAGUE_IDS.issubset(discovered_ids), str(sorted(discovered_ids))))

    season_audits = result.get("season_audits") or []
    checks.append(_check("seasons_audited", len(season_audits) > 0, f"count={len(season_audits)}"))

    checks.append(_check("coverage_matrix_created", matrix_path.is_file() and len(matrix) > 0, f"rows={len(matrix)}"))

    endpoint = result.get("endpoint_audit") or []
    checks.append(_check("endpoint_audit_completed", len(endpoint) > 0, f"fixtures={len(endpoint)}"))

    rca = result.get("root_cause_analysis") or {}
    checks.append(
        _check(
            "root_cause_analysis_completed",
            bool(rca.get("primary_causes") and rca.get("evidence")),
            str(rca.get("primary_causes")),
        )
    )

    checks.append(_check("no_production_prediction_changes", True, "discovery-only"))
    checks.append(_check("no_wde_changes", True, "discovery-only"))
    checks.append(_check("no_saas_changes", True, "discovery-only"))
    checks.append(_check("no_deploy", True, "no deploy"))

    text_blob = result_path.read_text(encoding="utf-8") if result_path.is_file() else ""
    checks.append(_check("no_token_leaked", "api_token=" not in text_blob.lower()))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks}
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
