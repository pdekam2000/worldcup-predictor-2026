#!/usr/bin/env python3
"""Validate Tier B WDE dependency recovery hotfix."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.gpt_actions.runtime_bootstrap import bootstrap_gpt_actions_runtime
from worldcup_predictor.gpt_actions.wde_runtime import attach_wde_execution_diagnostics
from worldcup_predictor.owner_daily.predictions import run_daily_wde

checks: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    src_bootstrap = (ROOT / "worldcup_predictor" / "gpt_actions" / "runtime_bootstrap.py").read_text(encoding="utf-8")
    src_predictions = (ROOT / "worldcup_predictor" / "owner_daily" / "predictions.py").read_text(encoding="utf-8")
    src_runtime = (ROOT / "worldcup_predictor" / "mcp_server" / "runtime.py").read_text(encoding="utf-8")
    src_worker = (ROOT / "worldcup_predictor" / "gpt_actions" / "worker.py").read_text(encoding="utf-8")

    record("bootstrap_auto_production_env", "_ensure_production_env" in src_bootstrap, "")
    record("bootstrap_clears_settings_cache", "get_settings.cache_clear" in src_bootstrap, "")
    record("worker_calls_bootstrap", "bootstrap_gpt_actions_runtime" in src_worker, "")
    record("runtime_calls_bootstrap", "bootstrap_gpt_actions_runtime" in src_runtime, "")
    record("specific_api_credentials_code", "WDE_API_CREDENTIALS_MISSING" in src_predictions, "")
    record("structured_diagnostics_helper", "attach_wde_execution_diagnostics" in src_predictions, "")
    record("btts_execution_status", "_market_execution_status" in src_runtime, "")
    record("ou_execution_status", "_market_execution_status" in src_runtime, "")
    record("no_wde_formula_change", "ScoringEngine" not in src_bootstrap, "")
    record("no_ecse_formula_change", "build_ecse_live_prediction" not in src_bootstrap, "")
    record("test_file_exists", (ROOT / "tests" / "gpt_actions" / "test_tier_b_wde_dependency_recovery.py").exists(), "")
    record("repro_report_exists", (ROOT / "TIER_B_WDE_DEPENDENCY_FAILURE_REPRODUCTION.md").exists(), "")
    record("chain_report_exists", (ROOT / "TIER_B_WDE_EXECUTION_CHAIN.md").exists(), "")
    record("matrix_report_exists", (ROOT / "TIER_B_WDE_DEPENDENCY_MATRIX.md").exists(), "")

    meta = bootstrap_gpt_actions_runtime()
    record("bootstrap_returns_metadata", "api_football_configured" in meta, str(meta.keys()))

    detail = attach_wde_execution_diagnostics(
        {},
        wde_execution_status="blocked_missing_dependency",
        failure_code="WDE_API_CREDENTIALS_MISSING",
        failure_dependency="api_credentials",
        failure_message_sanitized="test",
    )
    record("diagnostics_have_dependency", detail.get("wde_failure_dependency") == "api_credentials", "")
    record("diagnostics_no_generic_only", "WDE_DEPENDENCY_FAILED" not in str(detail.get("wde_failure_code")), "")

    sig = inspect.signature(run_daily_wde)
    record("run_daily_wde_signature_stable", "strict_fresh_odds" in sig.parameters, "")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"TIER_B_WDE_RECOVERY_VALIDATOR: {passed}/{total}")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail and not ok else ""
        print(f"  [{mark}] {name}{suffix}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
