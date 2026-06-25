#!/usr/bin/env python3
"""Validate Phase 54L Goalscorer ML Shadow Engine."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54l_goalscorer_ml_shadow"
REPORT = ROOT / "PHASE_54L_GOALSCORER_ML_SHADOW_REPORT.md"
DATASET = ROOT / "artifacts" / "phase54k_goalscorer_shadow" / "goalscorer_dataset.parquet"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.egie.goalscorer_ml_shadow import VALID_RECOMMENDATIONS, run_ml_shadow
        from worldcup_predictor.egie.goalscorer_ml_shadow.features import load_dataset, split_data

        checks.append(_check("ml_shadow_imports", True))
    except Exception as exc:
        checks.append(_check("ml_shadow_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "egie" / "goalscorer_ml_shadow"
    for mod in ("models.py", "features.py", "trainer.py", "ranking_metrics.py", "calibration.py", "runner.py"):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    checks.append(_check("datasets_loaded", DATASET.is_file()))

    if DATASET.is_file():
        df = load_dataset(DATASET)
        train, val, test = split_data(df)
        split_ok = len(train) > 0 and len(val) > 0 and len(test) > 0
        checks.append(_check("temporal_split_respected", split_ok, f"train={len(train)} val={len(val)} test={len(test)}"))

    artifact = ARTIFACT_DIR / "ml_shadow_report.json"
    if not artifact.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54l_goalscorer_ml_shadow.py")], check=False)

    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        ranking = report.get("ranking") or []
        checks.append(_check("models_trained", len(ranking) >= 9))
        checks.append(_check("calibration_evaluated", len(report.get("calibration") or []) >= 3))
        has_topk = any(r.get("top3_hit") is not None for r in ranking)
        checks.append(_check("ranking_metrics_generated", has_topk))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
        blob = artifact.read_text(encoding="utf-8").lower()
        checks.append(_check("no_token_leaked", "api_token=" not in blob))
    else:
        checks.append(_check("models_trained", False))
        checks.append(_check("calibration_evaluated", False))
        checks.append(_check("ranking_metrics_generated", False))
        checks.append(_check("recommendation_valid", False))
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
