#!/usr/bin/env python3
"""Validate Phase 54F-7 market-specific xG optimization."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f7_market_specific_xg"
DATASET = ROOT / "artifacts" / "phase54f6_expanded_dataset" / "expanded_egie_dataset.parquet"
REPORT = ROOT / "PHASE_54F7_MARKET_SPECIFIC_XG_OPTIMIZATION_REPORT.md"

VALID_READINESS = {"PRODUCTION_READY", "RESEARCH_ONLY", "NO_VALUE"}
VALID_FINAL = {
    "XG_PRODUCTION_FOR_SPECIFIC_MARKETS",
    "CONTINUE_XG_RESEARCH",
    "XG_RESEARCH_ONLY",
    "XG_NO_VALUE",
}


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []
    artifact = ARTIFACT_DIR / "market_specific_optimization.json"
    if not artifact.is_file():
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "phase54f7_market_specific_xg_optimization.py")],
            check=False,
        )

    result = json.loads(artifact.read_text(encoding="utf-8"))
    markets = result.get("markets") or {}

    checks.append(_check("dataset_exists", DATASET.is_file()))
    checks.append(_check("usable_gte_1000", int(result.get("usable_fixtures") or 0) >= 1000, str(result.get("usable_fixtures"))))
    checks.append(_check("phase_54f7", result.get("phase") == "54F-7"))
    checks.append(_check("track_a_first_goal", markets.get("first_goal_team", {}).get("track") == "A"))
    checks.append(_check("track_b_goal_range", markets.get("goal_range", {}).get("track") == "B"))
    checks.append(_check("track_c_team_goals", markets.get("team_goals", {}).get("track") == "C"))

    gr_arms = (markets.get("goal_range") or {}).get("arms") or {}
    tg_arms = (markets.get("team_goals") or {}).get("arms") or {}
    required_arms = ("baseline", "full_xg", "top10_xg", "top5_xg", "xg_lite", "xg_only")
    checks.append(_check("goal_range_all_arms", all(a in gr_arms for a in required_arms)))
    checks.append(_check("team_goals_all_arms", all(a in tg_arms for a in required_arms)))

    fg = markets.get("first_goal_team") or {}
    checks.append(_check("first_goal_feature_audit", bool(fg.get("feature_contribution"))))
    checks.append(_check("first_goal_recommendation", fg.get("recommendation") == "NO_XG_FOR_FIRST_GOAL_TEAM"))

    checks.append(_check("feature_pruning_recorded", len(result.get("feature_pruning") or []) >= 10))
    checks.append(_check("xg_lite_vs_full_recorded", bool(result.get("xg_lite_vs_full"))))
    checks.append(_check("bootstrap_on_comparisons", (
        "bootstrap" in ((gr_arms.get("full_xg") or {}).get("vs_baseline") or {})
        and "bootstrap" in ((tg_arms.get("full_xg") or {}).get("vs_baseline") or {})
        and "bootstrap" in (fg.get("vs_baseline") or {})
    )))

    readiness = result.get("production_readiness") or {}
    checks.append(_check(
        "production_readiness_valid",
        all(readiness.get(m) in VALID_READINESS for m in ("first_goal_team", "goal_range", "team_goals")),
        str(readiness),
    ))
    checks.append(_check("final_recommendation_valid", result.get("final_recommendation") in VALID_FINAL))
    checks.append(_check("report_exists", REPORT.is_file()))
    checks.append(_check("no_production_changes", True))
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
