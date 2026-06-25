#!/usr/bin/env python3
"""Phase 62 — full UI rebrand + super admin access validation."""

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


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    # --- Static file checks ---
    record(checks, "nav_config_exists", (SRC / "lib/navConfig.js").is_file())
    record(checks, "owner_login_page", (SRC / "pages/OwnerLogin.jsx").is_file())
    record(checks, "intelligence_components", (SRC / "components/intelligence/index.jsx").is_file())
    record(checks, "ensure_owner_script", (ROOT / "scripts/ensure_owner_super_admin.py").is_file())
    record(checks, "api_error_lib", (SRC / "lib/apiError.js").is_file())

    app_text = (SRC / "App.jsx").read_text(encoding="utf-8")
    record(checks, "route_owner_login", 'path="/owner-login"' in app_text)
    record(checks, "route_owner_alias", 'path="/system/owner-access"' in app_text)
    record(checks, "route_admin_dashboard_redirect", 'path="/admin/dashboard"' in app_text)

    required_routes = [
        "/dashboard",
        "/matches",
        "/goal-timing/dashboard",
        "/research/highlights",
        "/elite/world-cup",
        "/admin/elite-shadow",
        "/subscription",
        "/settings",
        "/accuracy",
        "/owner-login",
    ]
    for route in required_routes:
        record(checks, f"route_{route.strip('/').replace('/', '_')}", route in app_text, route)

    layout_text = (SRC / "components/dashboard/DashboardLayout.jsx").read_text(encoding="utf-8")
    record(checks, "layout_uses_nav_config", "buildNavSections" in layout_text)
    record(checks, "layout_uses_sidebar_nav", "SidebarNav" in layout_text)

    nav_text = (SRC / "lib/navConfig.js").read_text(encoding="utf-8")
    record(checks, "nav_no_duplicate_trophy_import", nav_text.count("Trophy") <= 8)
    record(checks, "nav_main_section", "MAIN_NAV_SECTION" in nav_text)
    record(checks, "nav_admin_elite_shadow", "/admin/elite-shadow" in nav_text)
    record(checks, "nav_elite_wc_super_admin", 'roles: ["super_admin"]' in nav_text and "/elite/world-cup" in nav_text)

    # Icon import validation for navConfig
    nav_icons = re.findall(r"icon:\s*(\w+)", nav_text)
    nav_imports = set(re.findall(r"\b(\w+)\b", nav_text.split("from \"lucide-react\"")[0]))
    missing_icons = [i for i in set(nav_icons) if i not in nav_imports]
    record(checks, "nav_icons_imported", not missing_icons, ", ".join(missing_icons) if missing_icons else "ok")

    # --- Frontend build ---
    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=180,
            shell=os.name == "nt",
        )
        record(checks, "npm_build", proc.returncode == 0, (proc.stderr or proc.stdout)[-400:])
    except Exception as exc:
        record(checks, "npm_build", False, str(exc))

    dist_index = FRONTEND / "dist" / "index.html"
    record(checks, "dist_index", dist_index.is_file())

    # --- Backend / API (optional) ---
    base_url = (os.environ.get("PHASE62_BASE_URL") or os.environ.get("API_BASE_URL") or "").rstrip("/")
    if base_url:
        try:
            import urllib.request

            for path, expect in [
                ("/api/health", (200,)),
                ("/api/research/highlights", (200,)),
                ("/api/goal-timing/dashboard", (200, 503)),
                ("/api/elite/world-cup/predictions", (401, 403)),
                ("/api/admin/elite-shadow/predictions", (401, 403)),
            ]:
                req = urllib.request.Request(f"{base_url}{path}")
                try:
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        record(checks, f"api_{path.strip('/').replace('/', '_')}", resp.status in expect, str(resp.status))
                except Exception as exc:
                    code = getattr(exc, "code", None)
                    record(checks, f"api_{path.strip('/').replace('/', '_')}", code in expect, str(code or exc))
        except Exception as exc:
            record(checks, "api_smoke", False, str(exc))
    else:
        record(checks, "api_smoke_skipped", True, "set PHASE62_BASE_URL for production smoke")

    # --- Owner account (local DB) ---
    try:
        from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow
        from worldcup_predictor.database.postgres.enums import UserRole

        if postgres_configured():
            with saas_uow() as uow:
                owner = uow.users.get_by_email("kamangar.pedram@gmail.com")
                record(
                    checks,
                    "owner_exists",
                    owner is not None,
                )
                if owner:
                    record(checks, "owner_super_admin", owner.role == UserRole.SUPER_ADMIN)
                    record(checks, "owner_active", owner.is_active and not owner.is_banned)
                    record(checks, "owner_email_verified", owner.email_verified)
        else:
            record(checks, "owner_db_skipped", True, "DATABASE_URL not set locally")
    except Exception as exc:
        record(checks, "owner_db_check", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase 62 validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
