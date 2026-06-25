#!/usr/bin/env python3
"""Phase 52D — Hybrid confidence validation checks."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "phase52d_confidence_validation.json"
ENGINE_REPORT = ROOT / "PHASE_52D_HYBRID_CONFIDENCE_ENGINE_REPORT.md"
VALIDATION_REPORT = ROOT / "PHASE_52D_VALIDATION_REPORT.md"
PROD_ENGINE = ROOT / "worldcup_predictor" / "goal_timing" / "engine.py"


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.egie.confidence import (
        HybridConfidenceEngine,
        HybridConfidenceShadowRunner,
        HybridConfidenceValidationRunner,
    )
    from worldcup_predictor.egie.confidence.config import HYBRID_CONFIDENCE_MODEL_VERSION
    from worldcup_predictor.egie.confidence.metrics import clamp01
    from worldcup_predictor.egie.guards import backtest_mode

    record("confidence_package_imports", True)
    record("hybrid_model_version_set", bool(HYBRID_CONFIDENCE_MODEL_VERSION))

    # Production engine untouched
    src = PROD_ENGINE.read_text(encoding="utf-8") if PROD_ENGINE.is_file() else ""
    record("production_engine_exists", "class EliteGoalTimingEngine" in src)
    record("no_hybrid_in_production_engine", "HybridConfidenceEngine" not in src)

    record("clamp01_sanity", clamp01(1.5) == 1.0 and clamp01(-0.1) == 0.0)

    with backtest_mode():
        runner = HybridConfidenceShadowRunner()
        rows = runner.run_from_survival_jsonl(persist=False)
    record("shadow_runner_scores", len(rows) >= 1, str(len(rows)))

    if rows:
        hc = rows[0].get("hybrid_confidence") or {}
        record("has_conf_team", hc.get("conf_team") is not None)
        record("has_conf_range", hc.get("conf_range") is not None)
        record("has_conf_minute", hc.get("conf_minute") is not None)
        record("has_tiers", bool(hc.get("tiers")))
        record("has_ui_model", bool(hc.get("ui")))
        record("shadow_mode_flag", hc.get("shadow_mode") is True)
        ui = hc.get("ui") or {}
        record("minute_experimental_badge", ui.get("minute_badge") == "Experimental")
        record("no_raw_pct_in_ui", "%" not in str(ui.get("team_label") or ""))

    if ARTIFACT.is_file():
        payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    else:
        with backtest_mode():
            payload = HybridConfidenceValidationRunner().run(persist_artifact=True)

    record("artifact_exists", payload.get("phase") == "52D")
    record("has_tier_calibration", bool(payload.get("tier_calibration")))
    record("has_distribution", bool(payload.get("distribution")))
    mono = payload.get("monotonicity") or {}
    record("monotonicity_evaluated", "overall_pass" in mono, str(mono.get("overall_pass")))
    record("legacy_cluster_reduced", (
        (payload.get("distribution") or {}).get("legacy_confidence", {}).get("at_0_65_pct", 100) > 50
        and (payload.get("distribution") or {}).get("conf_team", {}).get("at_0_65_pct", 100) < 50
    ))

    status = payload.get("phase_52d_status")
    record("phase_52d_status_set", status in ("SHADOW_VALIDATED", "PRODUCTION_ACTIVE"), str(status))

    if not payload.get("deploy_allowed"):
        record("deploy_blocked_when_not_monotonic", payload.get("production_active") is False)
    else:
        record("deploy_allowed_when_monotonic", payload.get("production_active") is True)

    record("engine_report_exists", ENGINE_REPORT.is_file())
    record("validation_report_exists", VALIDATION_REPORT.is_file())

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"Phase 52D validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
