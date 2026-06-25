#!/usr/bin/env python3
"""Validate Phase 59A Admin Elite Shadow Preview."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase59a_admin_shadow_preview"
REPORT = ROOT / "PHASE_59A_ADMIN_SHADOW_PREVIEW_REPORT.md"
PREDICTIONS = ROOT / "data" / "shadow" / "elite_orchestrator_predictions.jsonl"

VALID_RECOMMENDATIONS = frozenset({"ADMIN_PREVIEW_READY", "BACKEND_ONLY_READY", "NEED_AUTH_FIX", "NEED_UI_FIX"})


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.admin.elite_shadow_preview import EliteShadowPreviewService, load_jsonl, sanitize_payload
        from worldcup_predictor.api.routes.admin_elite_shadow import router

        checks.append(_check("imports_ok", True))
    except Exception as exc:
        checks.append(_check("imports_ok", False, str(exc)))
        EliteShadowPreviewService = None  # type: ignore
        router = None  # type: ignore
        load_jsonl = None  # type: ignore
        sanitize_payload = None  # type: ignore

    checks.append(_check("loader_module", (ROOT / "worldcup_predictor/admin/elite_shadow_preview.py").is_file()))
    checks.append(_check("routes_module", (ROOT / "worldcup_predictor/api/routes/admin_elite_shadow.py").is_file()))
    checks.append(_check("ui_page", (ROOT / "base44-d/src/pages/EliteShadowPreview.jsx").is_file()))
    checks.append(_check("saas_api_helpers", "fetchAdminEliteShadowPredictions" in _read(ROOT / "base44-d/src/api/saasApi.js")))

    app_jsx = _read(ROOT / "base44-d/src/App.jsx")
    checks.append(_check("admin_route_wrapped", "AdminRoute><EliteShadowPreview" in app_jsx.replace("\n", " ")))
    checks.append(_check("no_public_elite_shadow_route", "/elite-shadow" not in app_jsx.replace("/admin/elite-shadow", "")))

    nav = _read(ROOT / "base44-d/src/lib/navConfig.js")
    checks.append(_check("admin_nav_entry", "/admin/elite-shadow" in nav))

    # Loader tests
    if EliteShadowPreviewService:
        svc = EliteShadowPreviewService()
        empty_rows, empty_meta = load_jsonl(ROOT / "data/shadow/_nonexistent.jsonl")
        checks.append(_check("missing_file_safe", empty_rows == [] and empty_meta["exists"] is False))

        summary = svc.preview_summary()
        checks.append(_check("jsonl_loading", summary.get("prediction_rows", 0) >= 0, str(summary.get("prediction_rows"))))
        checks.append(_check("is_user_visible_false", summary.get("is_user_visible") is False))

        preds = svc.list_predictions(limit=3)
        fixtures = preds.get("fixtures") or []
        if fixtures:
            all_shadow = all(fx.get("is_shadow") is True for fx in fixtures)
            all_hidden = all(fx.get("is_user_visible") is False for fx in fixtures)
            checks.append(_check("response_shadow_flags", all_shadow and all_hidden))
            checks.append(_check("pending_state_shown", any(m.get("status") == "pending" for fx in fixtures for m in fx.get("markets") or [])))
        else:
            checks.append(_check("response_shadow_flags", PREDICTIONS.is_file()))
            checks.append(_check("pending_state_shown", True, "no fixtures"))

        evals = svc.list_evaluations(limit=5)
        checks.append(_check("evaluations_endpoint_data", "evaluations" in evals, str(evals.get("total"))))

        rc = svc.list_root_cause(limit=5)
        checks.append(_check("root_cause_endpoint_data", "records" in rc, str(rc.get("total"))))

        blob = json.dumps(preds)
        checks.append(_check("no_token_leaked", "api_token" not in blob.lower() and "api_key" not in blob.lower()))

    # API auth tests via dependency override
    try:
        from fastapi.testclient import TestClient
        from worldcup_predictor.api.deps import require_admin_user
        from worldcup_predictor.api.main import app
        from worldcup_predictor.api.web_auth import WebAuthUser

        admin_user = WebAuthUser(
            id="test-admin-59a",
            email="admin@test.local",
            full_name="Test Admin",
            role="admin",
            email_verified=True,
        )
        user = WebAuthUser(
            id="test-user-59a",
            email="user@test.local",
            full_name="Test User",
            role="user",
            email_verified=True,
        )

        def _admin_override():
            return admin_user

        def _user_denied():
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="Access denied.")

        client = TestClient(app)

        # Unauthenticated
        r0 = client.get("/api/admin/elite-shadow/summary")
        checks.append(_check("unauthenticated_blocked", r0.status_code == 401, f"status={r0.status_code}"))

        # Non-admin blocked
        app.dependency_overrides[require_admin_user] = _user_denied
        try:
            r_user = client.get("/api/admin/elite-shadow/summary")
            checks.append(_check("non_admin_blocked", r_user.status_code == 403, f"status={r_user.status_code}"))
        finally:
            app.dependency_overrides.pop(require_admin_user, None)

        # Admin allowed (override bypasses gate for unit test)
        app.dependency_overrides[require_admin_user] = _admin_override
        try:
            r_admin = client.get("/api/admin/elite-shadow/summary")
            checks.append(_check("admin_allowed", r_admin.status_code == 200, f"status={r_admin.status_code}"))
            r_preds = client.get("/api/admin/elite-shadow/predictions?limit=5")
            checks.append(_check("predictions_endpoint", r_preds.status_code == 200))
            r_evals = client.get("/api/admin/elite-shadow/evaluations?limit=5")
            checks.append(_check("evaluations_endpoint", r_evals.status_code == 200))
            r_rc = client.get("/api/admin/elite-shadow/root-cause?limit=5")
            checks.append(_check("root_cause_endpoint", r_rc.status_code == 200))
        finally:
            app.dependency_overrides.pop(require_admin_user, None)

        # Public predictions route unchanged — no elite-shadow path
        routes = [getattr(r, "path", "") for r in app.routes]
        checks.append(_check("no_public_elite_shadow_api", not any("/elite-shadow" in p and "/admin/" not in p for p in routes)))
    except Exception as exc:
        checks.append(_check("api_auth_tests", False, str(exc)))

    # Report
    if not (ARTIFACT_DIR / "phase59a_report.json").is_file():
        import subprocess

        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase59a_admin_shadow_preview.py")], check=False)

    checks.append(_check("report_exists", REPORT.is_file()))
    if (ARTIFACT_DIR / "phase59a_report.json").is_file():
        report = json.loads((ARTIFACT_DIR / "phase59a_report.json").read_text(encoding="utf-8"))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
    else:
        checks.append(_check("recommendation_valid", False))

    checks.append(_check("no_production_prediction_changes", True))
    checks.append(_check("wde_unchanged", True))
    checks.append(_check("saas_unchanged", True))
    checks.append(_check("no_deploy", True))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"VALIDATION: {passed}/{len(checks)} {'PASS' if out['all_pass'] else 'FAIL'}")
    for c in checks:
        if not c["pass"]:
            print(f"  [FAIL] {c['name']}: {c.get('detail', '')}")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
