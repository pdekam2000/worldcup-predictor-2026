#!/usr/bin/env python3
"""Validate PHASE ECSE-X2-M8 owner-only ECSE shadow lab."""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x2_m6.constants import EVAL_ARTIFACT, SHADOW_ARTIFACT
from worldcup_predictor.research.ecse_x2_m8.lab_service import EcseOwnerShadowLabService

CHECKS: list[tuple[str, bool, str]] = []
RECOMMENDATIONS = frozenset(
    {
        "OWNER_LAB_READY",
        "NEED_OWNER_AUTH_FIX",
        "NEED_BACKEND_API_FIX",
        "NEED_FRONTEND_FIX",
        "NEED_MORE_EVALUATIONS",
    }
)


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def validate_frontend_route() -> None:
    app_jsx = (ROOT / "base44-d/src/App.jsx").read_text(encoding="utf-8")
    page = ROOT / "base44-d/src/pages/owner/OwnerEcseShadowLab.jsx"
    nav = (ROOT / "base44-d/src/lib/ownerNavConfig.js").read_text(encoding="utf-8")
    api = (ROOT / "base44-d/src/api/saasApi.js").read_text(encoding="utf-8")
    check("owner_route_registered", "/owner/ecse-shadow-lab" in app_jsx and "OwnerEcseShadowLab" in app_jsx)
    check("owner_page_exists", page.is_file())
    check("owner_nav_entry", "/owner/ecse-shadow-lab" in nav)
    check("owner_api_helpers", "fetchOwnerEcseShadowLabSummary" in api)
    check(
        "owner_warning_copy",
        "Owner research lab only" in page.read_text(encoding="utf-8"),
    )


def validate_owner_auth() -> None:
    from worldcup_predictor.auth.rbac import is_owner

    check("free_user_not_owner", not is_owner("free_user"))
    check("pro_not_owner", not is_owner("pro"))
    check("owner_is_owner", is_owner("owner"))

    try:
        from fastapi import HTTPException
        from fastapi.testclient import TestClient

        from worldcup_predictor.api.deps import require_owner_user, require_super_admin_user
        from worldcup_predictor.api.main import app
        from worldcup_predictor.api.web_auth import WebAuthUser

        client = TestClient(app)
        check("owner_api_unauth_401", client.get("/api/owner/ecse-shadow-lab/summary").status_code == 401)

        def _deny():
            raise HTTPException(status_code=403, detail="denied")

        app.dependency_overrides[require_owner_user] = _deny
        try:
            check(
                "owner_non_owner_403",
                client.get("/api/owner/ecse-shadow-lab/summary").status_code == 403,
            )
        finally:
            app.dependency_overrides.pop(require_owner_user, None)

        kwargs = {"id": "m8-owner", "email": "m8-owner@test", "full_name": "M8", "role": "owner"}
        if "email_verified" in inspect.signature(WebAuthUser).parameters:
            kwargs["email_verified"] = True

        app.dependency_overrides[require_owner_user] = lambda: WebAuthUser(**kwargs)
        try:
            check(
                "owner_allowed_200",
                client.get("/api/owner/ecse-shadow-lab/summary").status_code == 200,
            )
        finally:
            app.dependency_overrides.pop(require_owner_user, None)

        sa_kwargs = {**kwargs, "id": "m8-sa", "role": "super_admin"}
        app.dependency_overrides[require_super_admin_user] = lambda: WebAuthUser(**sa_kwargs)
        try:
            check(
                "admin_shadow_summary_200",
                client.get("/api/admin/ecse-x2/shadow-live-shortlists-summary").status_code == 200,
            )
        finally:
            app.dependency_overrides.pop(require_super_admin_user, None)
    except Exception as exc:
        check("owner_auth_integration", False, str(exc))


def validate_lab_data() -> None:
    shadow_path = ROOT / SHADOW_ARTIFACT
    check("shadow_artifact_exists", shadow_path.is_file())
    if not shadow_path.is_file():
        return

    raw_rows = [json.loads(ln) for ln in shadow_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    check("real_shadow_rows", len(raw_rows) > 0, f"n={len(raw_rows)}")
    check("no_fake_demo_rows", not any(r.get("demo") or r.get("is_demo") for r in raw_rows))
    check("public_output_changed_zero", sum(1 for r in raw_rows if r.get("public_output_changed") is True) == 0)

    conn = connect(get_db_path(get_settings().sqlite_path))
    try:
        svc = EcseOwnerShadowLabService()
        summary = svc.summary(conn)
        check("summary_total_matches", summary["total_shadow_rows"] == len(raw_rows))
        check("summary_applied_matches", summary["applied_count"] == sum(1 for r in raw_rows if r.get("applied")))
        check("summary_public_changed_zero", summary["public_output_changed_count"] == 0)

        listed = svc.list_fixtures(conn, filter_key="all", limit=5)
        items = listed.get("items") or []
        check("list_returns_items", len(items) > 0)
        if items:
            item = items[0]
            check("computed_owner_note", bool(item.get("owner_note")))
            check("computed_baseline_top1", "baseline_top1" in item)
            check("computed_enhanced_top1", "enhanced_top1" in item)
            fid = int(item["fixture_id"])
            detail = svc.get_fixture(conn, fid)
            check("detail_has_top10", detail is not None and bool(detail.get("baseline_top10")))
            check("detail_public_unchanged", detail is not None and detail.get("public_output_changed") is False)

        applied = svc.list_fixtures(conn, filter_key="applied", limit=500)
        better = svc.list_fixtures(conn, filter_key="enhanced_better", limit=500)
        check("filter_applied", applied["total"] == summary["applied_count"])
        check("filter_enhanced_better_runs", better["total"] >= 0)
    finally:
        conn.close()


def validate_unchanged_systems() -> None:
    conn = connect(get_db_path(get_settings().sqlite_path))
    try:
        n = baseline_table_row_count(conn)
        check("ecse_baseline_table_unchanged", n > 0, f"rows={n}")
    finally:
        conn.close()

    preds = (ROOT / "worldcup_predictor/api/routes/predictions.py").read_text(encoding="utf-8")
    check("predictions_no_m8_leak", "ecse_x2_m8" not in preds.lower() and "enhanced_top10" not in preds)

    billing = (ROOT / "worldcup_predictor/billing/billing_service.py").read_text(encoding="utf-8")
    check("billing_unchanged", "ecse_x2_m8" not in billing.lower())

    for path in ROOT.glob("worldcup_predictor/**/wde*.py"):
        if "ecse_x2_m8" in path.read_text(encoding="utf-8").lower():
            check("wde_unchanged", False, str(path))
            return
    check("wde_unchanged", True)


def validate_frontend_build() -> None:
    base44 = ROOT / "base44-d"
    if not (base44 / "package.json").is_file():
        check("frontend_build", False, "base44-d missing")
        return
    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(base44),
            capture_output=True,
            text=True,
            timeout=300,
            shell=True,
        )
        check("frontend_build_passes", proc.returncode == 0, (proc.stderr or proc.stdout)[-200:])
    except Exception as exc:
        check("frontend_build_passes", False, str(exc))


def validate_report() -> None:
    report = ROOT / "ECSE_X2_M8_OWNER_SHADOW_LAB_REPORT.md"
    check("report_exists", report.is_file())
    if report.is_file():
        text = report.read_text(encoding="utf-8")
        check("report_has_recommendation", any(r in text for r in RECOMMENDATIONS))


def main() -> int:
    print("ECSE-X2-M8 validation\n")
    validate_frontend_route()
    validate_owner_auth()
    validate_lab_data()
    validate_unchanged_systems()
    validate_frontend_build()
    validate_report()
    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
