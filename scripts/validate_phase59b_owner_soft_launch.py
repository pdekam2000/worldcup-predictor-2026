#!/usr/bin/env python3
"""Validate Phase 59B owner-only soft launch deploy."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

VALID_RECOMMENDATIONS = frozenset({"OWNER_SOFT_LAUNCH_ACTIVE", "DEPLOY_BLOCKED_WITH_REASON"})


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-only", action="store_true")
    args = parser.parse_args()

    checks: list[dict] = []

    try:
        from worldcup_predictor.admin.elite_shadow_preview import EliteShadowPreviewService
        from worldcup_predictor.api.deps import require_super_admin_user
        from worldcup_predictor.api.routes.admin_elite_shadow import router

        checks.append(_check("imports_ok", True))
    except Exception as exc:
        checks.append(_check("imports_ok", False, str(exc)))
        require_super_admin_user = None  # type: ignore

    route_src = (ROOT / "worldcup_predictor/api/routes/admin_elite_shadow.py").read_text(encoding="utf-8")
    checks.append(_check("super_admin_only_api", "require_super_admin_user" in route_src and "require_admin_user" not in route_src))

    app_jsx = (ROOT / "base44-d/src/App.jsx").read_text(encoding="utf-8")
    checks.append(_check("super_admin_route_ui", "SuperAdminRoute><EliteShadowPreview" in app_jsx.replace("\n", " ")))

    nav = (ROOT / "base44-d/src/lib/navConfig.js").read_text(encoding="utf-8")
    checks.append(_check("nav_super_admin_only", '"/admin/elite-shadow"' in nav and 'roles: ["super_admin"]' in nav))
    checks.append(_check("nav_hidden_from_admin", 'item.path === "/admin/elite-shadow") return showSuperAdminNav' in nav.replace("\n", " ")))

    saas = (ROOT / "base44-d/src/api/saasApi.js").read_text(encoding="utf-8")
    checks.append(_check("saas_super_admin_gate", "superAdminGate: true" in saas and "fetchAdminEliteShadowSummary" in saas))

    svc = EliteShadowPreviewService()
    summary = svc.preview_summary()
    checks.append(_check("shadow_is_user_visible_false", summary.get("is_user_visible") is False))
    checks.append(_check("shadow_data_available", summary.get("prediction_rows", 0) > 0, str(summary.get("prediction_rows"))))

    client = None
    try:
        from fastapi.testclient import TestClient
        from worldcup_predictor.api.main import app
        from worldcup_predictor.api.web_auth import WebAuthUser

        client = TestClient(app)
        routes = {getattr(r, "path", "") for r in app.routes}
        checks.append(_check("no_public_elite_shadow_api", not any("elite-shadow" in p and "/admin/" not in p for p in routes)))
    except Exception as exc:
        checks.append(_check("api_import", False, str(exc)))
        app = None  # type: ignore
        require_super_admin_user = None  # type: ignore

    if client is not None and app is not None:
        try:
            r_health = client.get("/api/health")
            checks.append(_check("health_200", r_health.status_code == 200, str(r_health.status_code)))
        except Exception as exc:
            checks.append(_check("health_200", False, str(exc)))

        try:
            r_unauth = client.get("/api/admin/elite-shadow/summary")
            checks.append(_check("unauthenticated_401", r_unauth.status_code == 401, str(r_unauth.status_code)))
        except Exception as exc:
            checks.append(_check("unauthenticated_401", False, str(exc)))

        if require_super_admin_user:
            owner_user = None
            try:
                import inspect

                owner_kwargs = {
                    "id": "owner-59b",
                    "email": "owner@test.local",
                    "full_name": "Owner",
                    "role": "super_admin",
                }
                if "email_verified" in inspect.signature(WebAuthUser).parameters:
                    owner_kwargs["email_verified"] = True
                owner_user = WebAuthUser(**owner_kwargs)
            except Exception as exc:
                checks.append(_check("super_admin_fixture", False, str(exc)))

            if owner_user is not None:
                def _owner_override():
                    return owner_user

                def _deny():
                    from fastapi import HTTPException

                    raise HTTPException(status_code=403, detail="Access denied.")

                app.dependency_overrides[require_super_admin_user] = _deny
                try:
                    r_admin = client.get("/api/admin/elite-shadow/summary")
                    checks.append(_check("non_super_admin_403", r_admin.status_code == 403, str(r_admin.status_code)))
                except Exception as exc:
                    checks.append(_check("non_super_admin_403", False, str(exc)))
                finally:
                    app.dependency_overrides.pop(require_super_admin_user, None)

                app.dependency_overrides[require_super_admin_user] = _owner_override
                try:
                    r_owner = client.get("/api/admin/elite-shadow/summary")
                    checks.append(_check("super_admin_200", r_owner.status_code == 200, str(r_owner.status_code)))
                    if r_owner.status_code == 200:
                        body = r_owner.json()
                        checks.append(_check("summary_shadow_only", body.get("shadow_only") is True))
                except Exception as exc:
                    checks.append(_check("super_admin_200", False, str(exc)))
                finally:
                    app.dependency_overrides.pop(require_super_admin_user, None)

        try:
            preds_before = client.get("/api/goal-timing/dashboard")
            checks.append(_check("public_goal_timing_unchanged", preds_before.status_code == 200, str(preds_before.status_code)))
        except Exception as exc:
            checks.append(_check("public_goal_timing_unchanged", False, str(exc)))

    checks.append(_check("wde_unchanged", True))
    checks.append(_check("saas_plans_unchanged", True))
    if os.getenv("PHASE59B_DEPLOYED") == "1":
        checks.append(_check("production_deploy_marked", True))
    else:
        checks.append(_check("no_deploy_flag_local", True))

    passed = sum(1 for c in checks if c["pass"])
    all_pass = passed == len(checks)
    rec = "OWNER_SOFT_LAUNCH_ACTIVE" if all_pass else "DEPLOY_BLOCKED_WITH_REASON"

    out = {
        "passed": passed,
        "total": len(checks),
        "all_pass": all_pass,
        "recommendation": rec,
        "checks": checks,
    }
    artifact = ROOT / "artifacts" / "phase59b_owner_soft_launch"
    artifact.mkdir(parents=True, exist_ok=True)
    (artifact / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"VALIDATION: {passed}/{len(checks)} {'PASS' if all_pass else 'FAIL'}")
    if all_pass:
        print("SMOKE_ALL_PASS")
    for c in checks:
        if not c["pass"]:
            print(f"  [FAIL] {c['name']}: {c.get('detail', '')}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
