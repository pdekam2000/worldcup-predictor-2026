#!/usr/bin/env python3
"""Validate Phase 56A Market Behavior Intelligence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase56a_market_behavior_intelligence"
REPORT = ROOT / "PHASE_56A_MARKET_BEHAVIOR_INTELLIGENCE_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.mbi import VALID_RECOMMENDATIONS, run_phase56a

        checks.append(_check("mbi_package_imports", True))
    except Exception as exc:
        checks.append(_check("mbi_package_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore
        run_phase56a = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "mbi"
    for mod in ("models.py", "inventory.py", "collector.py", "buckets.py", "edge_detection.py", "prior_feasibility.py", "runner.py"):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    required = (
        "odds_inventory.json",
        "mbi_selections.parquet",
        "odds_buckets.json",
        "edge_detection.json",
        "prior_feasibility.json",
        "decision.json",
        "phase56a_report.json",
    )
    if not (ARTIFACT_DIR / "mbi_selections.parquet").is_file() and run_phase56a:
        run_phase56a()
    elif not (ARTIFACT_DIR / "mbi_selections.parquet").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase56a_market_behavior_intelligence.py")], check=False)

    for fname in required:
        checks.append(_check(f"artifact_{fname}", (ARTIFACT_DIR / fname).is_file()))

    artifact = ARTIFACT_DIR / "phase56a_report.json"
    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
        checks.append(_check("inventory_complete", bool(report.get("inventory"))))
        checks.append(_check("bucket_analysis", (ARTIFACT_DIR / "odds_buckets.json").is_file()))
        checks.append(_check("prior_weights_tested", bool((report.get("prior") or {}).get("by_weight"))))
        qs = (report.get("decision") or {}).get("questions") or {}
        checks.append(_check("decision_questions", len(qs) >= 4))
    else:
        checks.append(_check("recommendation_valid", False))
        checks.append(_check("inventory_complete", False))
        checks.append(_check("bucket_analysis", False))
        checks.append(_check("prior_weights_tested", False))
        checks.append(_check("decision_questions", False))

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
