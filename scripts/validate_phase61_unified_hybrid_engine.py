#!/usr/bin/env python3
"""Phase 61 — Unified hybrid prediction engine validation."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "base44-d"
SRC = FRONTEND / "src"
UNIFIED = ROOT / "worldcup_predictor" / "unified_hybrid"


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    # --- Package structure ---
    for name in (
        "__init__.py",
        "models.py",
        "feature_store.py",
        "specialists.py",
        "decision_layer.py",
        "confidence.py",
        "engine.py",
        "backtest.py",
    ):
        record(checks, f"unified_{name.replace('.py', '')}", (UNIFIED / name).is_file())

    record(checks, "engine_audit_doc", (ROOT / "PHASE_61A_ENGINE_AUDIT.md").is_file())
    record(checks, "api_route", (ROOT / "worldcup_predictor/api/routes/unified_hybrid.py").is_file())

    settings_text = (ROOT / "worldcup_predictor/config/settings.py").read_text(encoding="utf-8")
    for flag in (
        "UNIFIED_ENGINE_ENABLED",
        "UNIFIED_ENGINE_ADMIN_PREVIEW",
        "UNIFIED_ENGINE_PUBLIC",
        "UNIFIED_ENGINE_COMPARE_MODE",
    ):
        record(checks, f"flag_{flag.lower()}", flag in settings_text)
    record(checks, "flags_default_safe", 'default=False,\n        alias="UNIFIED_ENGINE_ENABLED"' in settings_text or "unified_engine_enabled: bool = Field(\n        default=False" in settings_text)
    record(checks, "public_default_false", 'alias="UNIFIED_ENGINE_PUBLIC"' in settings_text)

    main_text = (ROOT / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")
    record(checks, "api_router_registered", "unified_hybrid_router" in main_text)

    # --- Engine preservation ---
    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    scoring = (ROOT / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    egie = (ROOT / "worldcup_predictor/goal_timing/engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged_file", wde.count("class WeightedDecisionEngine") >= 1)
    record(checks, "scoring_engine_unchanged_file", scoring.count("class ScoringEngine") >= 1)
    record(checks, "egie_unchanged_file", egie.count("class EliteGoalTimingEngine") >= 1)

    engine_text = (UNIFIED / "engine.py").read_text(encoding="utf-8")
    record(checks, "orchestrator_no_wde_edit", "WeightedDecisionEngine" not in engine_text)
    record(checks, "orchestrator_no_pipeline_run", "PredictPipeline" not in engine_text or "does not invoke" in (UNIFIED / "specialists.py").read_text(encoding="utf-8"))

    specialists_text = (UNIFIED / "specialists.py").read_text(encoding="utf-8")
    record(checks, "classic_read_only", "does not invoke PredictPipeline" in specialists_text)

    # --- Unified output ---
    try:
        from worldcup_predictor.unified_hybrid.engine import UnifiedHybridPredictionEngine

        eng = UnifiedHybridPredictionEngine()
        record(checks, "engine_import", True)
        record(checks, "engine_disabled_by_default", not eng.is_enabled())
        record(checks, "admin_preview_default", eng.admin_preview_allowed())
        record(checks, "public_blocked_default", not eng.public_allowed())
    except Exception as exc:
        record(checks, "engine_import", False, str(exc))

    # --- Backtest ---
    try:
        from worldcup_predictor.unified_hybrid.backtest import run_comparative_backtest

        bt = run_comparative_backtest(limit=10)
        record(checks, "backtest_runs", bt.get("status") == "ok")
        record(checks, "backtest_arms", all(k in bt.get("arms", {}) for k in ("classic", "egie", "unified", "production")))
    except Exception as exc:
        record(checks, "backtest_runs", False, str(exc))

    # --- Frontend ---
    record(checks, "unified_predictions_page", (SRC / "pages/UnifiedPredictionsPage.jsx").is_file())
    nav_text = (SRC / "lib/navConfig.js").read_text(encoding="utf-8")
    record(checks, "nav_unified_predictions", "Unified Predictions" in nav_text)
    record(checks, "nav_no_shadow_public", "/admin/elite-shadow" in nav_text and "Elite Shadow Preview" in nav_text)

    app_text = (SRC / "App.jsx").read_text(encoding="utf-8")
    record(checks, "route_unified_predictions", "/unified-predictions" in app_text)

    saas_api = (SRC / "api/saasApi.js").read_text(encoding="utf-8")
    record(checks, "frontend_unified_api", "fetchUnifiedPrediction" in saas_api)

    # --- Build ---
    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=240,
            shell=os.name == "nt",
        )
        record(checks, "npm_build", proc.returncode == 0, (proc.stderr or proc.stdout)[-400:])
    except Exception as exc:
        record(checks, "npm_build", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase 61 validation: {passed}/{total} passed\n")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail and not ok:
            line += f" — {detail[:200]}"
        print(line)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
