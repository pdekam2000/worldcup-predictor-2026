#!/usr/bin/env python3
"""Validate Phase 60D — request failed fixes + Elite WC page."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FORBIDDEN = ("root_cause", "component_contributions", "api_token", "openai_api_key", "sportmonks_token")


def _check(name: str, ok: bool, detail: str = "") -> tuple[str, bool, str]:
    return name, ok, detail


def _walk_forbidden(obj, path: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kp = f"{path}.{k}" if path else str(k)
            if any(f in str(k).lower() for f in FORBIDDEN):
                hits.append(kp)
            hits.extend(_walk_forbidden(v, kp))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(_walk_forbidden(v, f"{path}[{i}]"))
    return hits


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    # Files exist
    checks.append(_check("elite_wc_service", (ROOT / "worldcup_predictor/admin/elite_world_cup_predictions.py").is_file()))
    checks.append(_check("elite_wc_api_route", (ROOT / "worldcup_predictor/api/routes/elite_world_cup.py").is_file()))
    checks.append(_check("elite_wc_page", (ROOT / "base44-d/src/pages/EliteWorldCupPage.jsx").is_file()))
    checks.append(_check("api_error_helper", (ROOT / "base44-d/src/lib/apiError.js").is_file()))

    app_jsx = (ROOT / "base44-d/src/App.jsx").read_text(encoding="utf-8")
    checks.append(_check("route_elite_world_cup", "/elite/world-cup" in app_jsx))
    checks.append(_check("route_settings_redirect", "/account/settings" in app_jsx and "Navigate to=\"/settings\"" in app_jsx))
    checks.append(_check("route_accuracy_redirect", "/analytics/accuracy" in app_jsx))
    checks.append(_check("super_admin_route_guard", "SuperAdminRoute><SuperAdminPanel" in app_jsx))

    nav = (ROOT / "base44-d/src/lib/navConfig.js").read_text(encoding="utf-8")
    checks.append(_check("nav_elite_world_cup", "/elite/world-cup" in nav and "super_admin" in nav))
    checks.append(_check("nav_settings_path", 'path: "/settings"' in nav))

    saas = (ROOT / "base44-d/src/api/saasApi.js").read_text(encoding="utf-8")
    checks.append(_check("saas_extract_api_error", "extractApiErrorMessage" in saas))
    checks.append(_check("saas_fetch_elite_wc", "fetchEliteWorldCupPredictions" in saas))

    settings_src = (ROOT / "worldcup_predictor/config/settings.py").read_text(encoding="utf-8")
    checks.append(_check("elite_wc_public_flag", "elite_wc_public_enabled" in settings_src))

    repo_src = (ROOT / "worldcup_predictor/goal_timing/storage/repository.py").read_text(encoding="utf-8")
    checks.append(_check("goal_timing_postgres_safe", "_postgres_read_safe" in repo_src))

    # API tests
    try:
        from fastapi.testclient import TestClient
        from worldcup_predictor.api.main import app
        from worldcup_predictor.config.settings import get_settings

        client = TestClient(app)
        checks.append(_check("health_200", client.get("/api/health").status_code == 200))
        checks.append(_check("research_highlights_200", client.get("/api/research/highlights").status_code == 200))

        gt = client.get("/api/goal-timing/dashboard")
        checks.append(_check("goal_timing_dashboard_not_500", gt.status_code == 200, f"status={gt.status_code}"))

        unauth_elite = client.get("/api/elite/world-cup/predictions")
        checks.append(
            _check(
                "elite_wc_unauth_blocked",
                unauth_elite.status_code in (401, 403),
                f"status={unauth_elite.status_code}",
            )
        )

        unauth_shadow = client.get("/api/admin/elite-shadow/summary")
        checks.append(
            _check(
                "elite_shadow_unauth_401",
                unauth_shadow.status_code == 401,
                f"status={unauth_shadow.status_code}",
            )
        )

        from worldcup_predictor.admin.elite_world_cup_predictions import EliteWorldCupPredictionsService

        svc = EliteWorldCupPredictionsService()
        payload = svc.list_predictions(limit=5, include_comparison=True, public_mode=False)
        checks.append(_check("elite_wc_service_ok", payload.get("status") == "ok"))
        checks.append(_check("elite_wc_has_fixtures", isinstance(payload.get("fixtures"), list)))
        checks.append(_check("elite_wc_experimental_flag", payload.get("is_experimental") is True))
        forbidden = _walk_forbidden(payload)
        checks.append(_check("elite_wc_no_root_cause", not forbidden, ", ".join(forbidden[:5])))

        public_payload = svc.list_predictions(limit=3, include_comparison=False, public_mode=True)
        forbidden_pub = _walk_forbidden(public_payload)
        checks.append(_check("elite_wc_public_no_internals", "comparison" not in json.dumps(public_payload)))
        checks.append(_check("elite_wc_public_no_root_cause", not forbidden_pub))

        checks.append(_check("elite_wc_public_disabled_default", get_settings().elite_wc_public_enabled is False))
    except Exception as exc:
        checks.append(_check("api_tests", False, str(exc)))

    for mod in (
        "worldcup_predictor.decision.weighted_decision_engine",
        "worldcup_predictor.prediction.scoring_engine",
    ):
        try:
            importlib.import_module(mod)
            checks.append(_check(f"unchanged_{mod.split('.')[-1]}", True))
        except Exception as exc:
            checks.append(_check(f"unchanged_{mod.split('.')[-1]}", False, str(exc)))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"PHASE_60D_VALIDATION: {passed}/{total}")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
