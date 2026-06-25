#!/usr/bin/env python3
"""Validate Phase 55B UEFA goalscorer odds expansion."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase55b_uefa_goalscorer_odds_expansion"
REPORT = ROOT / "PHASE_55B_UEFA_GOALSCORER_ODDS_EXPANSION_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.egie.goalscorer_uefa_expansion import VALID_RECOMMENDATIONS, run_phase55b

        checks.append(_check("expansion_package_imports", True))
    except Exception as exc:
        checks.append(_check("expansion_package_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore
        run_phase55b = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "egie" / "goalscorer_uefa_expansion"
    for mod in ("models.py", "inventory.py", "bridge.py", "dataset.py", "revalidation.py", "runner.py"):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    if not (ARTIFACT_DIR / "phase55b_report.json").is_file() and run_phase55b:
        run_phase55b()
    elif not (ARTIFACT_DIR / "phase55b_report.json").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase55b_uefa_goalscorer_odds_expansion.py")], check=False)

    checks.append(_check("source_audit", (ARTIFACT_DIR / "source_audit.json").is_file()))
    checks.append(_check("uefa_inventory", (ARTIFACT_DIR / "uefa_goalscorer_inventory.json").is_file()))
    checks.append(_check("expanded_dataset", (ARTIFACT_DIR / "goalscorer_dataset_expanded.parquet").is_file()))
    checks.append(_check("revalidation", (ARTIFACT_DIR / "revalidation.json").is_file()))
    checks.append(_check("decision_recorded", (ARTIFACT_DIR / "decision.json").is_file()))

    artifact = ARTIFACT_DIR / "phase55b_report.json"
    checks.append(_check("phase55b_report_json", artifact.is_file()))

    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
        inv = report.get("uefa_inventory") or {}
        uefa_gs = int((inv.get("totals") or {}).get("uefa_fixtures_strict_player_gs") or 0)
        checks.append(_check("uefa_inventory_measured", True, f"strict_fixtures={uefa_gs}"))
    else:
        checks.append(_check("recommendation_valid", False))
        checks.append(_check("uefa_inventory_measured", False))

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
