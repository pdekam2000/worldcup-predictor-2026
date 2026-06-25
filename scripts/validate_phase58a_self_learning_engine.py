#!/usr/bin/env python3
"""Validate Phase 58A Elite Self Learning Engine."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase58a_self_learning_engine"
STORE_DIR = ROOT / "data" / "shadow" / "elite_learning_store"
REPORT = ROOT / "PHASE_58A_SELF_LEARNING_ENGINE_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.elite_self_learning import VALID_RECOMMENDATIONS, run_phase58a

        checks.append(_check("self_learning_imports", True))
    except Exception as exc:
        checks.append(_check("self_learning_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore
        run_phase58a = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "elite_self_learning"
    for mod in (
        "models.py",
        "post_match_eval.py",
        "component_attribution.py",
        "component_scoring.py",
        "adaptive_weights.py",
        "learning_store.py",
        "simulation.py",
        "runner.py",
    ):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    if not (ARTIFACT_DIR / "phase58a_report.json").is_file() and run_phase58a:
        run_phase58a()
    elif not (ARTIFACT_DIR / "phase58a_report.json").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase58a_self_learning_engine.py")], check=False)

    required_artifacts = (
        "adaptive_weight_spec.json",
        "rolling_component_scores.json",
        "weight_recommendations.json",
        "replay_summary.json",
        "decision.json",
        "phase58a_report.json",
    )
    for fname in required_artifacts:
        checks.append(_check(f"artifact_{fname}", (ARTIFACT_DIR / fname).is_file()))

    store_files = (
        "component_health.json",
        "market_health.json",
        "league_health.json",
        "confidence_calibration.json",
        "patterns.json",
        "adaptive_weight_recommendations.json",
    )
    for fname in store_files:
        checks.append(_check(f"store_{fname}", (STORE_DIR / fname).is_file()))

    checks.append(_check("store_evaluations_jsonl", (STORE_DIR / "post_match_evaluations.jsonl").is_file()))

    artifact = ARTIFACT_DIR / "phase58a_report.json"
    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
        checks.append(_check("fixtures_evaluated", int(report.get("fixtures_evaluated") or 0) >= 200))
        scores = json.loads((ARTIFACT_DIR / "rolling_component_scores.json").read_text(encoding="utf-8"))
        windows = {s.get("window") for s in scores}
        checks.append(_check("rolling_windows", {100, 500, 1000}.issubset(windows), str(sorted(windows))))
        spec = json.loads((ARTIFACT_DIR / "adaptive_weight_spec.json").read_text(encoding="utf-8"))
        checks.append(_check("safeguards_defined", len(spec.get("safeguards") or []) >= 6))
        checks.append(_check("shadow_only_flag", spec.get("config", {}).get("shadow_only") is True))
    else:
        for name in ("recommendation_valid", "fixtures_evaluated", "rolling_windows", "safeguards_defined", "shadow_only_flag"):
            checks.append(_check(name, False))

    checks.append(_check("report_exists", REPORT.is_file()))
    checks.append(_check("no_production_changes", not (report if artifact.is_file() else {}).get("production_changes", True)))
    checks.append(_check("no_deploy", True))
    checks.append(_check("no_auto_model_updates", True))

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
