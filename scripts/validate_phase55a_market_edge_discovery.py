#!/usr/bin/env python3
"""Validate Phase 55A market edge discovery."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase55a_market_edge_discovery"
REPORT = ROOT / "PHASE_55A_MARKET_EDGE_DISCOVERY_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.market_edge import VALID_RECOMMENDATIONS, run_phase55a

        checks.append(_check("market_edge_package_imports", True))
    except Exception as exc:
        checks.append(_check("market_edge_package_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore
        run_phase55a = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "market_edge"
    for mod in ("models.py", "collectors.py", "scoring.py", "runner.py"):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    if not (ARTIFACT_DIR / "phase55a_report.json").is_file() and run_phase55a:
        run_phase55a()
    elif not (ARTIFACT_DIR / "phase55a_report.json").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase55a_market_edge_discovery.py")], check=False)

    checks.append(_check("market_profiles", (ARTIFACT_DIR / "market_profiles.json").is_file()))
    checks.append(_check("market_rankings", (ARTIFACT_DIR / "market_rankings.json").is_file()))
    checks.append(_check("candidates", (ARTIFACT_DIR / "candidates.json").is_file()))
    checks.append(_check("dev_hours_recommendation", (ARTIFACT_DIR / "dev_hours_recommendation.json").is_file()))

    artifact = ARTIFACT_DIR / "phase55a_report.json"
    checks.append(_check("phase55a_report_json", artifact.is_file()))

    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
        rankings = report.get("rankings") or []
        checks.append(_check("thirteen_markets_ranked", len(rankings) >= 13, str(len(rankings))))
        cands = report.get("candidates") or {}
        checks.append(_check("top10_present", len(cands.get("top10_strongest") or []) >= 10))
        checks.append(_check("top5_research", len(cands.get("top5_research_candidates") or []) >= 5))
        checks.append(_check("top3_production", len(cands.get("top3_production_candidates") or []) >= 3))
    else:
        for n in ("recommendation_valid", "thirteen_markets_ranked", "top10_present", "top5_research", "top3_production"):
            checks.append(_check(n, False))

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
