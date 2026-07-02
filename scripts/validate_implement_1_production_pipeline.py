#!/usr/bin/env python3
"""IMPLEMENT-1 — Validate production prediction pipeline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PHASE = "IMPLEMENT-1-VALIDATION"
SYSTEMD_DIR = ROOT / "deployment" / "systemd"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    # 1. Runner imports
    try:
        from worldcup_predictor.owner.production_pipeline.runner import (  # noqa: F401
            PipelineConfig,
            run_production_prediction_pipeline,
        )

        checks.append(_check("runner_imports", True))
    except Exception as exc:
        checks.append(_check("runner_imports", False, str(exc)))

    # 2. Dry-run daily
    try:
        from worldcup_predictor.owner.production_pipeline.runner import PipelineConfig, run_production_prediction_pipeline

        dr = run_production_prediction_pipeline(
            PipelineConfig(mode="daily", dry_run=True, skip_lock=True, include_shadow_monitor=False)
        )
        checks.append(_check("dry_run_daily", dr.dry_run and not dr.errors, json.dumps(dr.counts)))
    except Exception as exc:
        checks.append(_check("dry_run_daily", False, str(exc)))

    # 3. Lock prevents overlap (fcntl platforms only)
    try:
        import fcntl  # noqa: F401

        from worldcup_predictor.owner.production_pipeline.lock import ProductionPipelineLock

        p = Path("data/locks/_validate_pipeline_lock_test.lock")
        a = ProductionPipelineLock(p)
        b = ProductionPipelineLock(p)
        ok1 = a.acquire()
        ok2 = b.acquire()
        a.release()
        checks.append(_check("lock_prevents_overlap", ok1 and not ok2, f"first={ok1} second={ok2}"))
    except ImportError:
        checks.append(_check("lock_prevents_overlap", True, "skipped_no_fcntl_windows"))
    except Exception as exc:
        checks.append(_check("lock_prevents_overlap", False, str(exc)))

    # 4-7. Mode smoke tests (dry-run)
    for mode in ("predictions-only", "results-only", "eval-only"):
        try:
            from worldcup_predictor.owner.production_pipeline.runner import PipelineConfig, run_production_prediction_pipeline

            r = run_production_prediction_pipeline(
                PipelineConfig(mode=mode, dry_run=True, skip_lock=True, include_shadow_monitor=False)
            )
            checks.append(_check(f"mode_{mode.replace('-', '_')}_dry_run", not r.errors, r.recommendation))
        except Exception as exc:
            checks.append(_check(f"mode_{mode.replace('-', '_')}_dry_run", False, str(exc)))

    # 8. No duplicate requirement — stored count stable on dry-run
    try:
        from worldcup_predictor.owner.production_pipeline.runner import PipelineConfig, run_production_prediction_pipeline

        r = run_production_prediction_pipeline(
            PipelineConfig(mode="predictions-only", dry_run=True, skip_lock=True, include_shadow_monitor=False)
        )
        stable = r.counts.get("stored_before") == r.counts.get("stored_after")
        checks.append(_check("dry_run_no_stored_prediction_growth", stable, str(r.counts)))
    except Exception as exc:
        checks.append(_check("dry_run_no_stored_prediction_growth", False, str(exc)))

    # 9-12. Structural checks via import / file presence
    checks.append(_check("pipeline_script_exists", (ROOT / "scripts/run_production_prediction_pipeline.py").exists()))
    checks.append(_check("systemd_daily_service", (SYSTEMD_DIR / "worldcup-prediction-daily.service").exists()))
    checks.append(_check("systemd_daily_timer", (SYSTEMD_DIR / "worldcup-prediction-daily.timer").exists()))
    checks.append(_check("systemd_hourly_service", (SYSTEMD_DIR / "worldcup-results-hourly.service").exists()))
    checks.append(_check("systemd_hourly_timer", (SYSTEMD_DIR / "worldcup-results-hourly.timer").exists()))

    # 13. Safety labels in runner output
    try:
        from worldcup_predictor.owner.production_pipeline.runner import SAFETY

        checks.append(_check("no_public_shadow_exposure_flag", SAFETY.get("ODDALERTS_ECSE_SHADOW_ONLY") is True))
        checks.append(_check("no_wde_retrain_flag", SAFETY.get("WDE_RETRAINED") is False))
    except Exception as exc:
        checks.append(_check("safety_labels", False, str(exc)))

    # 14. compileall quick
    cp = subprocess.run(
        [sys.executable, "-m", "compileall", "worldcup_predictor/owner/production_pipeline", "-q"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    checks.append(_check("compileall_pipeline_module", cp.returncode == 0, cp.stderr[:200]))

    # 15. Existing commands still import
    for mod in (
        "worldcup_predictor.owner_daily.cycle",
        "worldcup_predictor.owner_predict_eval.runner",
        "worldcup_predictor.automation.worldcup_background.auto_evaluation_job",
    ):
        try:
            __import__(mod)
            checks.append(_check(f"import_{mod.split('.')[-1]}", True))
        except Exception as exc:
            checks.append(_check(f"import_{mod.split('.')[-1]}", False, str(exc)))

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    ok = passed == total
    out = {
        "phase": PHASE,
        "passed": passed,
        "total": total,
        "all_passed": ok,
        "checks": checks,
        "recommendation": "IMPLEMENT_1_READY_TO_ENABLE_TIMERS" if ok else "IMPLEMENT_1_VALIDATION_FAILED",
    }
    artifact = ROOT / "artifacts" / "validate_implement_1_production_pipeline.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
