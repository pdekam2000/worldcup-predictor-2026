#!/usr/bin/env python3
"""Phase 63 — enterprise platform validation."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "base44-d"


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    record(checks, "rbac_module", (ROOT / "worldcup_predictor/auth/rbac.py").is_file())
    record(checks, "owner_routes", (ROOT / "worldcup_predictor/api/routes/owner.py").is_file())
    record(checks, "owner_service", (ROOT / "worldcup_predictor/owner/platform_service.py").is_file())
    record(checks, "migration_script", (ROOT / "scripts/migrate_phase63_enterprise_roles.py").is_file())
    record(checks, "ensure_owner_script", (ROOT / "scripts/ensure_owner_account.py").is_file())
    record(checks, "alembic_014", (ROOT / "alembic/versions/014_enterprise_rbac.py").is_file())

    record(checks, "frontend_rbac", (FRONTEND / "src/lib/rbac.js").is_file())
    record(checks, "owner_layout", (FRONTEND / "src/components/owner/OwnerLayout.jsx").is_file())
    record(checks, "owner_command_center", (FRONTEND / "src/pages/owner/OwnerCommandCenter.jsx").is_file())
    record(checks, "owner_autonomous_page", (FRONTEND / "src/pages/owner/OwnerAutonomousPage.jsx").is_file())

    deps = (ROOT / "worldcup_predictor/api/deps.py").read_text(encoding="utf-8")
    record(checks, "require_owner_user", "require_owner_user" in deps)
    record(checks, "deps_uses_rbac", "from worldcup_predictor.auth.rbac import" in deps)

    app = (FRONTEND / "src/App.jsx").read_text(encoding="utf-8")
    record(checks, "route_owner", 'path="/owner"' in app)
    record(checks, "route_owner_autonomous", 'path="/owner/autonomous"' in app)

    enums = (ROOT / "worldcup_predictor/database/postgres/enums.py").read_text(encoding="utf-8")
    record(checks, "enum_owner", "OWNER = " in enums)

    try:
        from worldcup_predictor.auth.rbac import is_owner, role_inherits

        record(checks, "owner_inherits_super", role_inherits("super_admin", "owner"))
        record(checks, "owner_inherits_admin", role_inherits("admin", "owner"))
        record(checks, "guest_not_admin", not role_inherits("admin", "guest"))
        record(checks, "is_owner_helper", is_owner("owner"))
    except Exception as exc:
        record(checks, "rbac_import", False, str(exc))

    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=180,
            shell=os.name == "nt",
        )
        record(checks, "npm_build", proc.returncode == 0, (proc.stderr or proc.stdout)[-300:])
    except Exception as exc:
        record(checks, "npm_build", False, str(exc))

    base = (os.environ.get("PHASE63_BASE_URL") or "").rstrip("/")
    if base:
        import urllib.request

        for path, expect in [
            ("/api/health", (200,)),
            ("/api/owner/overview", (401, 403)),
            ("/api/owner/autonomous/status", (401, 403)),
            ("/api/owner/monitoring", (401, 403)),
            ("/owner", (200, 302)),
            ("/owner-login", (200,)),
        ]:
            try:
                with urllib.request.urlopen(f"{base}{path}", timeout=20) as resp:
                    record(checks, f"http_{path.strip('/').replace('/', '_')}", resp.status in expect, str(resp.status))
            except Exception as exc:
                code = getattr(exc, "code", None)
                record(checks, f"http_{path.strip('/').replace('/', '_')}", code in expect, str(code or exc))
    else:
        record(checks, "prod_smoke_skipped", True, "set PHASE63_BASE_URL")

    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

    if postgres_configured():
        try:
            from worldcup_predictor.database.postgres.enums import UserRole

            with saas_uow() as uow:
                owner = uow.users.get_by_email("kamangar.pedram@gmail.com")
                if owner:
                    record(checks, "owner_account_exists", True)
                    record(checks, "owner_role", owner.role == UserRole.OWNER, owner.role.value)
                else:
                    record(checks, "owner_account_exists", False, "run ensure_owner_account.py")
        except Exception as exc:
            record(checks, "owner_db", False, str(exc))
    else:
        record(checks, "owner_db_skipped", True, "no DATABASE_URL")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase 63 validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print()
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
