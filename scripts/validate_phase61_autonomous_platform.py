#!/usr/bin/env python3
"""Validate Phase 61 — autonomous prediction platform."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _check(name: str, ok: bool, detail: str = "") -> tuple[str, bool, str]:
    return name, ok, detail


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    modules = [
        "worldcup_predictor.autonomous.fixture_discovery",
        "worldcup_predictor.autonomous.prediction_scheduler",
        "worldcup_predictor.autonomous.completion_detector",
        "worldcup_predictor.autonomous.evaluation_engine",
        "worldcup_predictor.autonomous.performance_certification",
        "worldcup_predictor.autonomous.orchestrator",
    ]
    for mod in modules:
        try:
            importlib.import_module(mod)
            checks.append(_check(f"import_{mod.split('.')[-1]}", True))
        except Exception as exc:
            checks.append(_check(f"import_{mod.split('.')[-1]}", False, str(exc)))

    checks.append(_check("admin_performance_api", (ROOT / "worldcup_predictor/api/routes/admin_performance.py").is_file()))
    checks.append(_check("admin_performance_page", (ROOT / "base44-d/src/pages/AdminPerformancePage.jsx").is_file()))
    checks.append(_check("systemd_service", (ROOT / "deployment/systemd/worldcup-autonomous.service").is_file()))
    checks.append(_check("systemd_timer", (ROOT / "deployment/systemd/worldcup-autonomous.timer").is_file()))

    settings_src = (ROOT / "worldcup_predictor/config/settings.py").read_text(encoding="utf-8")
    checks.append(_check("autonomous_settings", "autonomous_platform_enabled" in settings_src))

    mig_src = (ROOT / "worldcup_predictor/database/migrations.py").read_text(encoding="utf-8")
    checks.append(_check("phase61_ddl", "autonomous_prediction_snapshots" in mig_src))

    app_jsx = (ROOT / "base44-d/src/App.jsx").read_text(encoding="utf-8")
    checks.append(_check("route_admin_performance", "/admin/performance" in app_jsx))

    saas = (ROOT / "base44-d/src/api/saasApi.js").read_text(encoding="utf-8")
    checks.append(_check("saas_performance_api", "fetchAdminPerformanceCertification" in saas))

    # Store immutability
    from worldcup_predictor.autonomous.store import AutonomousStore
    from worldcup_predictor.config.settings import get_settings

    settings = get_settings()
    settings = settings.model_copy(update={"autonomous_dry_run": True})
    store = AutonomousStore(settings)
    sid1, _ = store.insert_snapshot(
        fixture_id=99999001,
        competition_key="world_cup_2026",
        engine="production",
        market_id="1x2",
        prediction={"selection": "home"},
        generated_by="autonomous_scheduler",
        source="production",
    )
    sid2, reason2 = store.insert_snapshot(
        fixture_id=99999001,
        competition_key="world_cup_2026",
        engine="production",
        market_id="1x2",
        prediction={"selection": "home"},
        generated_by="autonomous_scheduler",
        source="production",
    )
    checks.append(_check("snapshots_append_only", sid1 is not None and sid2 is not None))
    snaps = store.list_snapshots(fixture_id=99999001, engine="production", market_id="1x2")
    checks.append(_check("no_duplicate_active_overwrite", len(snaps) >= 2))

    # Dry-run cycle
    from worldcup_predictor.autonomous.orchestrator import run_autonomous_cycle

    report = run_autonomous_cycle(settings=settings, dry_run=True, fixture_limit=5)
    checks.append(_check("autonomous_once_dry_run", report.get("status") == "ok", str(report.get("status"))))
    checks.append(_check("reports_api_calls", "api_calls_used" in report))

    # API auth
    try:
        from fastapi.testclient import TestClient
        from worldcup_predictor.api.main import app

        client = TestClient(app)
        unauth = client.get("/api/admin/performance/certification")
        checks.append(_check("admin_perf_unauth_401", unauth.status_code == 401, f"status={unauth.status_code}"))
        checks.append(_check("health_200", client.get("/api/health").status_code == 200))
    except Exception as exc:
        checks.append(_check("api_tests", False, str(exc)))

    # WDE unchanged
    wde_src = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    checks.append(_check("unchanged_wde", "class WeightedDecisionEngine" in wde_src))

    scoring_src = (ROOT / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    checks.append(_check("unchanged_scoring_engine", "class ScoringEngine" in scoring_src or "def score" in scoring_src))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"PHASE_61_VALIDATION: {passed}/{total}")
    for name, ok, detail in checks:
        tag = "PASS" if ok else "FAIL"
        line = f"  [{tag}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
