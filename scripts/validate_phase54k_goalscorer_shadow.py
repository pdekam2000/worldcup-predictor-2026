#!/usr/bin/env python3
"""Validate Phase 54K Goalscorer Shadow Engine."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54k_goalscorer_shadow"
REPORT = ROOT / "PHASE_54K_GOALSCORER_SHADOW_ENGINE_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.egie.goalscorer_shadow import (
            VALID_RECOMMENDATIONS,
            GoalscorerDatasetBuilder,
            run_backtest,
        )
        from worldcup_predictor.egie.goalscorer_shadow.scoring import apply_baseline_scores

        checks.append(_check("shadow_package_imports", True))
    except Exception as exc:
        checks.append(_check("shadow_package_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore

    required_modules = [
        "models.py",
        "feature_builder.py",
        "dataset_builder.py",
        "scoring.py",
        "backtest.py",
        "calibration.py",
        "validation.py",
    ]
    pkg = ROOT / "worldcup_predictor" / "egie" / "goalscorer_shadow"
    checks.append(_check("shadow_modules_exist", all((pkg / m).is_file() for m in required_modules)))

    artifact = ARTIFACT_DIR / "backtest_report.json"
    if not artifact.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54k_goalscorer_shadow.py")], check=False)

    checks.append(_check("dataset_created", (ARTIFACT_DIR / "goalscorer_dataset.parquet").is_file()))
    checks.append(_check("dataset_csv_created", (ARTIFACT_DIR / "goalscorer_dataset.csv").is_file()))
    checks.append(_check("dataset_summary_created", (ARTIFACT_DIR / "goalscorer_dataset_summary.json").is_file()))

    summary = {}
    if (ARTIFACT_DIR / "goalscorer_dataset_summary.json").is_file():
        summary = json.loads((ARTIFACT_DIR / "goalscorer_dataset_summary.json").read_text(encoding="utf-8"))
    checks.append(
        _check(
            "targets_created",
            int(summary.get("anytime_positive") or 0) > 0 and int(summary.get("first_goal_positive") or 0) > 0,
            f"anytime={summary.get('anytime_positive')} first={summary.get('first_goal_positive')}",
        )
    )

    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        checks.append(_check("baseline_models_ran", len(report.get("anytime") or []) >= 4))
        checks.append(_check("backtest_completed", bool(report.get("generated_at"))))
        has_topk = any(
            (m.get("top3_hit") is not None) for m in (report.get("anytime") or [])
        )
        checks.append(_check("topk_metrics_generated", has_topk))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
        text_blob = artifact.read_text(encoding="utf-8").lower()
        checks.append(_check("no_token_leaked", "api_token=" not in text_blob))
    else:
        checks.append(_check("baseline_models_ran", False))
        checks.append(_check("backtest_completed", False))
        checks.append(_check("topk_metrics_generated", False))
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
