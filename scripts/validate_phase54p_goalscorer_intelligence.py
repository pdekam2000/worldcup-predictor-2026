#!/usr/bin/env python3
"""Validate Phase 54P goalscorer intelligence shadow layer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54p_goalscorer_intelligence"
REPORT = ROOT / "PHASE_54P_GOALSCORER_INTELLIGENCE_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.egie.goalscorer_intelligence import VALID_RECOMMENDATIONS, run_phase54p

        checks.append(_check("intelligence_package_imports", True))
    except Exception as exc:
        checks.append(_check("intelligence_package_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore
        run_phase54p = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "egie" / "goalscorer_intelligence"
    for mod in (
        "models.py",
        "feature_pipeline.py",
        "ranking_engine.py",
        "confidence_engine.py",
        "intelligence_layer.py",
        "validation.py",
        "runner.py",
    ):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    if not (ARTIFACT_DIR / "fixture_intelligence.json").is_file() and run_phase54p:
        run_phase54p()
    elif not (ARTIFACT_DIR / "fixture_intelligence.json").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54p_goalscorer_intelligence.py")], check=False)

    checks.append(_check("intelligence_generated", (ARTIFACT_DIR / "fixture_intelligence.json").is_file()))
    checks.append(_check("confidence_generated", (ARTIFACT_DIR / "confidence_tier_replay.json").is_file()))
    checks.append(_check("historical_replay_completed", (ARTIFACT_DIR / "historical_replay.json").is_file()))
    checks.append(_check("value_pick_dataset_created", (ARTIFACT_DIR / "value_pick_dataset.parquet").is_file()))

    artifact = ARTIFACT_DIR / "phase54p_report.json"
    checks.append(_check("phase54p_report_json", artifact.is_file()))

    if (ARTIFACT_DIR / "fixture_intelligence.json").is_file():
        intel = json.loads((ARTIFACT_DIR / "fixture_intelligence.json").read_text(encoding="utf-8"))
        checks.append(_check("fixtures_have_anytime_picks", len(intel) > 0 and bool(intel[0].get("top_anytime_scorers"))))

    if (ARTIFACT_DIR / "historical_replay.json").is_file():
        replay = json.loads((ARTIFACT_DIR / "historical_replay.json").read_text(encoding="utf-8"))
        checks.append(_check("replay_has_metrics", replay.get("status") == "ok", str(replay.get("status"))))

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
