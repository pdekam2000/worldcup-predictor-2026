#!/usr/bin/env python3
"""Validate Phase 60A full production deploy (GUI + shadow comparison)."""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-only", action="store_true")
    args = parser.parse_args()

    checks: list[dict] = []

    route_src = _read(ROOT / "worldcup_predictor/api/routes/admin_elite_shadow.py")
    checks.append(_check("comparison_endpoint_in_routes", "/comparison" in route_src))
    checks.append(_check("super_admin_only_api", "require_super_admin_user" in route_src))

    ui = _read(ROOT / "base44-d/src/pages/EliteShadowPreview.jsx")
    checks.append(_check("comparison_ui_section", "Shadow vs Production" in ui))
    checks.append(_check("comparison_fetch_ui", "fetchAdminEliteShadowComparison" in ui))

    saas = _read(ROOT / "base44-d/src/api/saasApi.js")
    checks.append(_check("saas_comparison_helper", "fetchAdminEliteShadowComparison" in saas))

    try:
        from worldcup_predictor.admin.elite_shadow_comparison import EliteShadowComparisonService
        from worldcup_predictor.admin.elite_shadow_preview import EliteShadowPreviewService
        from worldcup_predictor.api.deps import require_super_admin_user
        from worldcup_predictor.api.main import app
        from worldcup_predictor.api.web_auth import WebAuthUser
        from fastapi.testclient import TestClient

        svc = EliteShadowPreviewService()
        summary = svc.preview_summary()
        checks.append(_check("shadow_is_user_visible_false", summary.get("is_user_visible") is False))

        comp = EliteShadowComparisonService().build_comparison(limit=10)
        checks.append(_check("comparison_builds", comp.get("status") == "ok"))
    except Exception as exc:
        checks.append(_check("backend_imports", False, str(exc)))
        app = None
        require_super_admin_user = None
        WebAuthUser = None  # type: ignore

    if app is not None and require_super_admin_user is not None:
        client = TestClient(app)
        r0 = client.get("/api/admin/elite-shadow/comparison")
        checks.append(_check("unauthenticated_401", r0.status_code == 401, str(r0.status_code)))

        owner_kwargs = {"id": "o60a", "email": "o@test", "full_name": "O", "role": "super_admin"}
        if WebAuthUser and "email_verified" in inspect.signature(WebAuthUser).parameters:
            owner_kwargs["email_verified"] = True

        def _deny():
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="denied")

        def _owner():
            return WebAuthUser(**owner_kwargs)

        app.dependency_overrides[require_super_admin_user] = _deny
        try:
            r403 = client.get("/api/admin/elite-shadow/comparison")
            checks.append(_check("non_super_admin_403", r403.status_code == 403, str(r403.status_code)))
        finally:
            app.dependency_overrides.pop(require_super_admin_user, None)

        app.dependency_overrides[require_super_admin_user] = _owner
        try:
            r200 = client.get("/api/admin/elite-shadow/comparison?limit=5")
            checks.append(_check("super_admin_comparison_200", r200.status_code == 200, str(r200.status_code)))
        finally:
            app.dependency_overrides.pop(require_super_admin_user, None)

        routes = {getattr(r, "path", "") for r in app.routes}
        checks.append(_check("no_public_comparison", not any("elite-shadow" in p and "/admin/" not in p for p in routes)))

    checks.append(_check("wde_unchanged", "class WeightedDecisionEngine" in _read(ROOT / "worldcup_predictor/decision/weighted_decision_engine.py")))

    passed = sum(1 for c in checks if c["pass"])
    all_pass = passed == len(checks)
    out = {"passed": passed, "total": len(checks), "all_pass": all_pass, "checks": checks}

    if all_pass:
        print("SMOKE_ALL_PASS" if args.smoke_only else "VALIDATION_ALL_PASS")
    else:
        print("SMOKE_HAS_FAILURES" if args.smoke_only else "VALIDATION_FAIL")
        for c in checks:
            if not c["pass"]:
                print(f"  FAIL {c['name']}: {c.get('detail')}")

    artifact = ROOT / "artifacts" / "phase60a_full_deploy"
    artifact.mkdir(parents=True, exist_ok=True)
    (artifact / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
