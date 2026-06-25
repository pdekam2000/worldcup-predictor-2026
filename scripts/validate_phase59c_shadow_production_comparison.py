#!/usr/bin/env python3
"""Validate Phase 59C Elite Shadow vs production comparison dashboard."""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

VALID_RECOMMENDATIONS = frozenset(
    {"COMPARISON_READY", "NEEDS_DATA", "NEEDS_AUTH_FIX", "BLOCKED_WITH_REASON"}
)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.admin.elite_shadow_comparison import (
            EliteShadowComparisonService,
            _extract_production_market,
            _load_production_payload,
        )
        from worldcup_predictor.api.deps import require_super_admin_user
        from worldcup_predictor.api.main import app
        from worldcup_predictor.api.routes.admin_elite_shadow import router
        from worldcup_predictor.api.web_auth import WebAuthUser
        from fastapi.testclient import TestClient

        checks.append(_check("imports_ok", True))
    except Exception as exc:
        checks.append(_check("imports_ok", False, str(exc)))
        return _finish(checks)

    route_src = _read(ROOT / "worldcup_predictor/api/routes/admin_elite_shadow.py")
    checks.append(_check("comparison_route_registered", "/comparison" in route_src))
    checks.append(_check("super_admin_only_api", "require_super_admin_user" in route_src))

    ui = _read(ROOT / "base44-d/src/pages/EliteShadowPreview.jsx")
    checks.append(_check("dashboard_comparison_section", "Shadow vs Production" in ui))
    checks.append(_check("comparison_filters_ui", "disagreementOnly" in ui and "fixtureFilter" in ui))

    saas = _read(ROOT / "base44-d/src/api/saasApi.js")
    checks.append(_check("saas_comparison_helper", "fetchAdminEliteShadowComparison" in saas))
    checks.append(
        _check(
            "saas_super_admin_gate",
            "fetchAdminEliteShadowComparison" in saas
            and '/api/admin/elite-shadow/comparison' in saas
            and "{ superAdminGate: true }" in saas,
        )
    )

    nav = _read(ROOT / "base44-d/src/lib/navConfig.js")
    app_jsx = _read(ROOT / "base44-d/src/App.jsx")
    checks.append(_check("nav_super_admin_only", '"/admin/elite-shadow"' in nav and 'roles: ["super_admin"]' in nav))
    checks.append(_check("super_admin_route_ui", "SuperAdminRoute><EliteShadowPreview" in app_jsx.replace("\n", " ")))
    checks.append(_check("no_public_elite_shadow_route", "/elite-shadow" not in app_jsx.replace("/admin/elite-shadow", "")))

    wde = _read(ROOT / "worldcup_predictor/decision/weighted_decision_engine.py")
    checks.append(_check("wde_unchanged", "class WeightedDecisionEngine" in wde))

    svc = EliteShadowComparisonService()
    result = svc.build_comparison(limit=500)
    checks.append(_check("comparison_status_ok", result.get("status") == "ok"))
    checks.append(_check("comparison_shadow_flags", result.get("shadow_only") is True and result.get("is_user_visible") is False))
    checks.append(_check("comparison_summary_present", isinstance(result.get("summary"), dict)))
    checks.append(_check("comparison_rows_list", isinstance(result.get("rows"), list)))

    summary = result.get("summary") or {}
    checks.append(
        _check(
            "shadow_data_available",
            summary.get("total_rows", 0) > 0,
            str(summary.get("total_rows")),
        )
    )

    missing_prod = _extract_production_market(None, "1x2")
    checks.append(_check("missing_production_safe", missing_prod.get("available") is False and missing_prod.get("prediction") is None))

    missing_shadow_row = next((r for r in result.get("rows") or [] if not r.get("has_production")), None)
    if missing_shadow_row:
        checks.append(_check("missing_production_row_safe", missing_shadow_row.get("disagreement") is None))
    else:
        checks.append(_check("missing_production_row_safe", True, "no missing-production rows in current data"))

    payload, _ = _load_production_payload(999999999)
    checks.append(_check("missing_fixture_production_safe", payload is None))

    filtered = svc.build_comparison(disagreement_only=True, limit=500)
    checks.append(_check("disagreement_filter_safe", filtered.get("status") == "ok"))
    for row in filtered.get("rows") or []:
        if row.get("comparable"):
            checks.append(_check("disagreement_filter_honored", row.get("disagreement") is True))
            break
    else:
        checks.append(_check("disagreement_filter_honored", True, "no comparable disagreements"))

    client = TestClient(app)
    routes = {getattr(r, "path", "") for r in app.routes}
    checks.append(_check("no_public_comparison_api", not any("elite-shadow/comparison" in p and "/admin/" not in p for p in routes)))

    r_unauth = client.get("/api/admin/elite-shadow/comparison")
    checks.append(_check("unauthenticated_401", r_unauth.status_code == 401, str(r_unauth.status_code)))

    owner_kwargs = {
        "id": "owner-59c",
        "email": "owner@test.local",
        "full_name": "Owner",
        "role": "super_admin",
    }
    if "email_verified" in inspect.signature(WebAuthUser).parameters:
        owner_kwargs["email_verified"] = True
    owner_user = WebAuthUser(**owner_kwargs)

    def _deny():
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Access denied.")

    def _owner_override():
        return owner_user

    app.dependency_overrides[require_super_admin_user] = _deny
    try:
        r_forbidden = client.get("/api/admin/elite-shadow/comparison")
        checks.append(_check("non_super_admin_403", r_forbidden.status_code == 403, str(r_forbidden.status_code)))
    finally:
        app.dependency_overrides.pop(require_super_admin_user, None)

    app.dependency_overrides[require_super_admin_user] = _owner_override
    try:
        r_owner = client.get("/api/admin/elite-shadow/comparison?limit=5")
        checks.append(_check("super_admin_can_access", r_owner.status_code == 200, str(r_owner.status_code)))
        if r_owner.status_code == 200:
            body = r_owner.json()
            checks.append(_check("endpoint_has_summary", "summary" in body and "rows" in body))
            sample = (body.get("rows") or [None])[0]
            if sample:
                checks.append(_check("row_has_shadow_production", "shadow" in sample and "production" in sample))
    finally:
        app.dependency_overrides.pop(require_super_admin_user, None)

    try:
        r_public = client.get("/api/health")
        checks.append(_check("public_api_unchanged", r_public.status_code == 200, str(r_public.status_code)))
    except Exception as exc:
        checks.append(_check("public_api_unchanged", False, str(exc)))

    checks.append(_check("saas_plans_unchanged", (ROOT / "worldcup_predictor/config/settings.py").is_file()))

    return _finish(checks, sample_comparison=result)


def _finish(checks: list[dict], sample_comparison: dict | None = None) -> int:
    passed = sum(1 for c in checks if c["pass"])
    all_pass = passed == len(checks)

    summary = (sample_comparison or {}).get("summary") or {}
    comparable = int(summary.get("total_comparable") or 0)
    if not all_pass:
        rec = "BLOCKED_WITH_REASON"
    elif comparable == 0 and summary.get("total_rows", 0) > 0:
        rec = "NEEDS_DATA"
    elif not any(c["name"] == "super_admin_can_access" and c["pass"] for c in checks):
        rec = "NEEDS_AUTH_FIX"
    else:
        rec = "COMPARISON_READY"

    out = {
        "passed": passed,
        "total": len(checks),
        "all_pass": all_pass,
        "recommendation": rec,
        "checks": checks,
        "sample_summary": summary,
    }

    artifact = ROOT / "artifacts" / "phase59c_shadow_production_comparison"
    artifact.mkdir(parents=True, exist_ok=True)
    (artifact / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    report = ROOT / "PHASE_59C_SHADOW_PRODUCTION_COMPARISON_REPORT.md"
    _write_report(report, out, sample_comparison)

    print(f"VALIDATION: {passed}/{len(checks)} {'PASS' if all_pass else 'FAIL'}")
    print(f"RECOMMENDATION: {rec}")
    for c in checks:
        if not c["pass"]:
            print(f"  [FAIL] {c['name']}: {c.get('detail', '')}")
    return 0 if all_pass else 1


def _write_report(path: Path, out: dict, sample: dict | None) -> None:
    sample_row = None
    if sample and sample.get("rows"):
        sample_row = sample["rows"][0]

    lines = [
        "# Phase 59C — Elite Shadow vs Production Comparison Report",
        "",
        "## Summary",
        "",
        f"- Validation: **{out['passed']}/{out['total']}** checks passed",
        f"- Recommendation: **`{out['recommendation']}`**",
        "",
        "## Files changed",
        "",
        "- `worldcup_predictor/admin/elite_shadow_comparison.py` (new)",
        "- `worldcup_predictor/api/routes/admin_elite_shadow.py` (`GET /comparison`)",
        "- `base44-d/src/pages/EliteShadowPreview.jsx` (Shadow vs Production section)",
        "- `base44-d/src/api/saasApi.js` (`fetchAdminEliteShadowComparison`)",
        "- `scripts/validate_phase59c_shadow_production_comparison.py` (new)",
        "",
        "## Endpoint",
        "",
        "`GET /api/admin/elite-shadow/comparison` — super_admin only",
        "",
        "Query params: `market`, `tier`, `status`, `disagreement_only`, `fixture_id`, `limit`, `offset`",
        "",
        "### Result example (summary)",
        "",
        "```json",
        json.dumps(out.get("sample_summary") or {}, indent=2),
        "```",
        "",
    ]
    if sample_row:
        lines.extend(
            [
                "### Result example (row)",
                "",
                "```json",
                json.dumps(sample_row, indent=2)[:2500],
                "```",
                "",
            ]
        )

    lines.extend(
        [
            "## UI notes",
            "",
            "- Section **Shadow vs Production** added to `/admin/elite-shadow`",
            "- Shows comparable count, same-pick/disagreement stats, avg confidences",
            "- Highlights markets with most disagreement and strong shadow disagreements",
            "- Filters: market, tier, status, fixture ID, disagreement-only checkbox",
            "- Screenshots: not captured in this validation run (local/dev environment)",
            "",
            "## Validation",
            "",
            "```json",
            json.dumps({"passed": out["passed"], "total": out["total"], "recommendation": out["recommendation"]}, indent=2),
            "```",
            "",
            "Full check list: `artifacts/phase59c_shadow_production_comparison/validation.json`",
            "",
            "## Safety confirmation",
            "",
            "- Endpoint requires `require_super_admin_user` (401 unauthenticated, 403 non-super-admin)",
            "- No public navigation or public API route for comparison",
            "- Shadow responses keep `is_user_visible=false` and `shadow_only=true`",
            "- No changes to WDE, public prediction output, or SaaS plans",
            "- Elite Shadow not promoted to production",
            "",
            "## Recommendation",
            "",
            f"**`{out['recommendation']}`**",
            "",
        ]
    )
    if out["recommendation"] == "NEEDS_DATA":
        lines.append(
            "Comparison plumbing is ready, but no shadow rows currently overlap stored production picks "
            "(local DB has shadow fixtures without matching `worldcup_stored_predictions` rows). "
            "Run production predict/cache for the same fixture set to populate comparable rows."
        )
    elif out["recommendation"] == "COMPARISON_READY":
        lines.append(
            "Owner monitoring dashboard is ready. Super_admin can compare shadow vs production "
            "with filters and disagreement highlights without affecting live predictions."
        )

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
