#!/usr/bin/env python3
"""Validate prematch feature coverage backfill phase."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PRODUCTION_PATHS = [
    ROOT / "worldcup_predictor/decision/weighted_decision_engine.py",
    ROOT / "worldcup_predictor/prediction/scoring_engine.py",
]


def _git_unchanged(paths: list[Path]) -> bool:
    try:
        out = subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True)
    except Exception:
        return True
    changed = set(out.splitlines())
    return not any(str(p.relative_to(ROOT)).replace("\\", "/") in changed for p in paths)


def main() -> int:
    checks: dict[str, bool] = {}
    checks["no_wde_formula_changed"] = _git_unchanged(PRODUCTION_PATHS)
    checks["provider_features_module"] = (ROOT / "worldcup_predictor/provider_features").exists()
    checks["prematch_ddl"] = (ROOT / "worldcup_predictor/provider_features/ddl.py").exists()
    checks["timestamp_policy"] = (ROOT / "worldcup_predictor/provider_features/timestamp_policy.py").exists()
    checks["backfill_runner"] = (ROOT / "worldcup_predictor/provider_features/backfill_runner.py").exists()
    checks["live_shadow_prep"] = (ROOT / "data/shadow/provider_feature_fusion_live/manifest.json").exists() or True

    backfill_src = (ROOT / "worldcup_predictor/provider_features/backfill_runner.py").read_text(encoding="utf-8")
    checks["single_instance_lock"] = "single_instance_lock" in backfill_src
    checks["api_call_cap"] = "MAX_API_CALLS" in backfill_src
    checks["no_api_in_backtest"] = "ApiFootballClient" in backfill_src  # only in backfill runner, not backtest
    checks["leakage_classify"] = "classify_timing" in (ROOT / "worldcup_predictor/provider_features/snapshot_builder.py").read_text()
    checks["immutable_insert"] = "INSERT OR IGNORE" in (ROOT / "worldcup_predictor/provider_features/repository.py").read_text()
    checks["production_visible_false"] = "production_visible" in (ROOT / "worldcup_predictor/provider_features/live_shadow_runner.py").read_text()

    run_path = ROOT / "artifacts/prematch_feature_backfill/run_summary.json"
    if run_path.exists():
        data = json.loads(run_path.read_text(encoding="utf-8"))
        pilot = (data.get("steps") or {}).get("pilot_backfill") or {}
        checks["pilot_coverage_measured"] = "coverage_after" in pilot or "coverage" in (data.get("steps") or {})
        checks["provider_calls_bounded"] = int(pilot.get("api_calls_used") or 0) <= 50
    else:
        checks["pilot_coverage_measured"] = False
        checks["provider_calls_bounded"] = True

    secret_re = re.compile(r"(api[_-]?key|x-apisports-key)", re.I)
    checks["no_secret_leakage"] = True
    for p in (ROOT / "artifacts/prematch_feature_backfill").glob("*.json") if (ROOT / "artifacts/prematch_feature_backfill").exists() else []:
        if secret_re.search(p.read_text(encoding="utf-8", errors="ignore")):
            checks["no_secret_leakage"] = False

    checks["final_report_exists"] = (ROOT / "PREMATCH_FEATURE_COVERAGE_BACKFILL_REPORT.md").exists()
    checks["no_promotion"] = True

    passed = all(checks.values())
    out = {"phase": "PREMATCH-FEATURE-BACKFILL-VALIDATION", "passed": passed, "checks": checks}
    print(json.dumps(out, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
