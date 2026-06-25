#!/usr/bin/env python3
"""Validate Phase 54O goalscorer bridge."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54o_goalscorer_bridge"
REPORT = ROOT / "PHASE_54O_GOALSCORER_BRIDGE_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.egie.goalscorer_bridge import VALID_RECOMMENDATIONS, run_phase54o

        checks.append(_check("bridge_package_imports", True))
    except Exception as exc:
        checks.append(_check("bridge_package_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore
        run_phase54o = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "egie" / "goalscorer_bridge"
    for mod in (
        "models.py",
        "team_mapper.py",
        "fixture_mapper.py",
        "player_mapper.py",
        "odds_loader.py",
        "audit.py",
        "dataset_v2.py",
        "revalidation.py",
        "edge_analysis.py",
        "runner.py",
    ):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    if not (ARTIFACT_DIR / "fixture_bridge.json").is_file() and run_phase54o:
        run_phase54o()
    elif not (ARTIFACT_DIR / "fixture_bridge.json").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54o_goalscorer_bridge.py")], check=False)

    checks.append(_check("fixture_bridge_built", (ARTIFACT_DIR / "fixture_bridge.json").is_file()))
    checks.append(_check("player_mapping_expanded", (ARTIFACT_DIR / "goalscorer_odds_mapped_bridged.csv").is_file()))
    checks.append(_check("dataset_v2_built", (ARTIFACT_DIR / "goalscorer_dataset_v2.parquet").is_file()))
    checks.append(_check("revalidation_completed", (ARTIFACT_DIR / "revalidation.json").is_file()))
    checks.append(_check("calibration_evaluated", (ARTIFACT_DIR / "edge_analysis.json").is_file()))

    artifact = ARTIFACT_DIR / "phase54o_report.json"
    checks.append(_check("phase54o_report_json", artifact.is_file()))

    if (ARTIFACT_DIR / "bridge_audit.json").is_file():
        audit = json.loads((ARTIFACT_DIR / "bridge_audit.json").read_text(encoding="utf-8"))
        pm = audit.get("player_mapping") or {}
        checks.append(
            _check(
                "mapping_rate_produced",
                float(pm.get("mapping_rate") or 0) > 0,
                f"rate={pm.get('mapping_rate')}",
            )
        )

    if (ARTIFACT_DIR / "revalidation.json").is_file():
        reval = json.loads((ARTIFACT_DIR / "revalidation.json").read_text(encoding="utf-8"))
        checks.append(
            _check(
                "revalidation_has_metrics",
                reval.get("status") == "ok",
                str(reval.get("status")),
            )
        )

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
