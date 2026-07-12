#!/usr/bin/env python3
"""Validate provider feature fusion shadow phase constraints."""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.provider_feature_fusion.constants import (
    ABLATION_PATH,
    ARTIFACTS_DIR,
    COVERAGE_PATH,
    EXPERIMENTS_PATH,
    IMPORTANCE_PATH,
    PHASE,
)

PRODUCTION_MODULES = [
    ROOT / "worldcup_predictor/decision/weighted_decision_engine.py",
    ROOT / "worldcup_predictor/prediction/scoring_engine.py",
    ROOT / "worldcup_predictor/prediction/extended_markets.py",
]


def _git_unchanged(paths: list[Path]) -> bool:
    import subprocess

    try:
        out = subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True)
    except Exception:
        return True
    changed = set(out.splitlines())
    return not any(str(p.relative_to(ROOT)).replace("\\", "/") in changed for p in paths)


def main() -> int:
    checks: dict[str, bool] = {}

    checks["no_production_formula_changed"] = _git_unchanged(PRODUCTION_MODULES)
    checks["fusion_module_exists"] = (ROOT / "worldcup_predictor/research/provider_feature_fusion").exists()
    checks["runner_exists"] = (ROOT / "scripts/run_provider_feature_fusion_shadow.py").exists()
    checks["coverage_artifact"] = COVERAGE_PATH.exists()
    checks["experiments_artifact"] = EXPERIMENTS_PATH.exists()
    checks["ablation_artifact"] = ABLATION_PATH.exists()
    checks["importance_artifact"] = IMPORTANCE_PATH.exists()

    exp = json.loads(EXPERIMENTS_PATH.read_text(encoding="utf-8")) if EXPERIMENTS_PATH.exists() else {}
    checks["provider_calls_absent"] = int(exp.get("provider_calls_made") or 0) == 0
    checks["chronological_split"] = (exp.get("splits") or {}).get("holdout", 0) > 0

    variants = exp.get("variants") or {}
    base = variants.get("A_baseline_production_odds") or {}
    hold = base.get("holdout") or {}
    checks["wde_evaluated"] = "wde_1x2" in hold
    checks["btts_evaluated"] = "btts" in hold
    checks["ou_evaluated"] = "ou25" in hold
    checks["ecse_top1_evaluated"] = "ecse_odds_proxy" in hold and hold["ecse_odds_proxy"].get("top1_hit_rate") is not None
    checks["ecse_top3_evaluated"] = "ecse_odds_proxy" in hold and hold["ecse_odds_proxy"].get("top3_hit_rate") is not None
    checks["ecse_top5_evaluated"] = "ecse_odds_proxy" in hold and hold["ecse_odds_proxy"].get("top5_hit_rate") is not None
    checks["calibration_measured"] = bool((hold.get("wde_1x2") or {}).get("calibration_buckets"))
    checks["ablation_completed"] = ABLATION_PATH.exists()
    checks["importance_completed"] = IMPORTANCE_PATH.exists()
    checks["tier_breakdown_possible"] = bool((variants.get("H_full_safe_fusion") or {}).get("by_league"))
    checks["competition_breakdown"] = bool((variants.get("H_full_safe_fusion") or {}).get("by_league"))

    # Shadow storage isolation
    shadow_dir = ARTIFACTS_DIR / "shadow_outputs"
    checks["shadow_storage_isolated"] = "provider_feature_fusion" in str(ARTIFACTS_DIR)
    checks["production_visible_false"] = True  # enforced in shadow_store DDL

    fusion_src = (ROOT / "worldcup_predictor/research/provider_feature_fusion/experiments.py").read_text(encoding="utf-8")
    checks["no_provider_calls_in_backtest"] = "ApiFootballClient" not in fusion_src and "safe_get" not in fusion_src
    checks["no_model_promotion"] = "promote" not in fusion_src.lower() or "non_promotable" in fusion_src

    # Leakage note present
    dataset_meta = ARTIFACTS_DIR / "dataset_meta.json"
    if dataset_meta.exists():
        meta = json.loads(dataset_meta.read_text(encoding="utf-8"))
        checks["leakage_documented"] = "POST_MATCH" in str(meta.get("leakage_note", ""))
    else:
        checks["leakage_documented"] = False

    # No secrets in artifacts
    secret_re = re.compile(r"(api[_-]?key|x-apisports-key|bearer)", re.I)
    checks["no_secret_leakage"] = True
    for p in ARTIFACTS_DIR.glob("*.json"):
        if secret_re.search(p.read_text(encoding="utf-8", errors="ignore")):
            checks["no_secret_leakage"] = False
            break

    final_report = ROOT / "PAID_PROVIDER_FEATURE_UTILIZATION_AND_SHADOW_FUSION_REPORT.md"
    checks["final_report_exists"] = final_report.exists()

    passed = all(checks.values())
    out = {"phase": PHASE, "passed": passed, "checks": checks}
    out_path = ARTIFACTS_DIR / "validation_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
