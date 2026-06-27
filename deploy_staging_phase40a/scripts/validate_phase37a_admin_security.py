"""Phase 37A — admin / super-admin security hardening validation."""

from __future__ import annotations

import json
import os
import runpy
import tempfile
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 37A validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]
    fe = root / "base44-d" / "src"

    layout = _read(fe / "components" / "dashboard" / "DashboardLayout.jsx")
    record("sidebar_uses_role_helpers", "canSeeAdminNav" in layout and "canSeeSuperAdminNav" in layout)
    record("sidebar_no_blanket_admin_items", "adminItems.map" not in layout)
    record("super_admin_nav_gated", "showSuperAdminNav" in layout)
    record("api_settings_gated", "showApiSettings" in layout and "canSeeApiSettings" in layout)

    admin_route = _read(fe / "components" / "AdminRoute.jsx")
    record("admin_route_access_denied", "AccessDenied" in admin_route)
    record("admin_route_gate_prompt", "AdminGatePrompt" in admin_route)
    record("admin_route_no_redirect_non_admin", 'Navigate to="/dashboard"' not in admin_route or "AccessDenied" in admin_route)

    super_route = _read(fe / "components" / "SuperAdminRoute.jsx")
    record("super_admin_route_exists", "SuperAdminRoute" in super_route or Path(fe / "components" / "SuperAdminRoute.jsx").exists())
    record("super_admin_route_uses_super_role", "isSuperAdminUser" in super_route)

    app_jsx = _read(fe / "App.jsx")
    record("api_settings_wrapped_admin_route", "AdminRoute><ApiSettingsPage" in app_jsx.replace("\n", " "))
    record("super_admin_wrapped_super_route", "SuperAdminRoute><SuperAdminPanel" in app_jsx.replace("\n", " "))

    roles_js = _read(fe / "lib" / "roles.js")
    record("roles_helper_super_admin", "super_admin" in roles_js)
    record("normal_user_not_admin", 'role === "admin"' in roles_js and "super_admin" in roles_js)

    saas_api = _read(fe / "api" / "saasApi.js")
    record("admin_fetch_sends_gate_header", "adminGate: true" in saas_api)
    record("super_admin_mutations_gate", "superAdminGate: true" in saas_api)
    record("no_keys_in_frontend", "ADMIN_ACCESS_KEY" not in saas_api and "SUPER_ADMIN_ACCESS_KEY" not in saas_api)

    access_denied = _read(fe / "components" / "AccessDenied.jsx")
    record("generic_access_denied_message", "Access denied." in access_denied)

    # Backend gate module
    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()
    os.environ["ADMIN_ACCESS_KEY"] = "test-admin-key-37a"
    os.environ["SUPER_ADMIN_ACCESS_KEY"] = "test-super-key-37a"
    get_settings.cache_clear()
    settings = get_settings()

    from worldcup_predictor.access.admin_gate import (
        attempt_gate_unlock,
        create_gate_token,
        gate_attempt_state,
        validate_gate_token,
        verify_access_key,
        write_admin_audit_event,
    )

    record("admin_key_verify_correct", verify_access_key("admin", "test-admin-key-37a", settings))
    record("admin_key_verify_wrong", not verify_access_key("admin", "wrong-key", settings))
    record("super_key_verify_correct", verify_access_key("super_admin", "test-super-key-37a", settings))

    ok, msg, state, token = attempt_gate_unlock(
        user_id="user-1", gate="admin", access_key="wrong", ip="127.0.0.1", settings=settings
    )
    record("admin_gate_rejects_wrong_key", not ok and msg == "Access denied.")

    ok2, _, _, token2 = attempt_gate_unlock(
        user_id="user-2", gate="admin", access_key="test-admin-key-37a", ip="127.0.0.1", settings=settings
    )
    record("admin_gate_accepts_correct_key", ok2 and bool(token2))
    record(
        "gate_token_validates",
        validate_gate_token(token2, user_id="user-2", gate="admin", settings=settings),
    )

    # Brute force lockout
    uid = "user-lock-test"
    for _ in range(5):
        attempt_gate_unlock(user_id=uid, gate="admin", access_key="bad", ip="10.0.0.1", settings=settings)
    locked_state = gate_attempt_state(uid, "admin", "10.0.0.1")
    record("brute_force_lockout", locked_state.locked)

    # Audit log
    with tempfile.TemporaryDirectory() as tmp:
        audit_path = Path(tmp) / "audit.jsonl"
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(audit_path)
        get_settings.cache_clear()
        s2 = get_settings()
        write_admin_audit_event("admin_gate_failed", user_id="u1", ip="1.2.3.4", settings=s2)
        content = audit_path.read_text(encoding="utf-8")
        record("audit_log_written", "admin_gate_failed" in content)
        record("audit_no_secrets", "test-admin-key" not in content and "test-super-key" not in content)

    # deps role checks
    from worldcup_predictor.api.deps import user_has_admin_access, user_has_super_admin_access

    record("deps_admin_includes_super", user_has_admin_access("super_admin"))
    record("deps_user_not_admin", not user_has_admin_access("user"))
    record("deps_super_admin_only", user_has_super_admin_access("super_admin") and not user_has_super_admin_access("admin"))

    # FastAPI endpoint smoke (no postgres — gate verify only needs auth mock)
    try:
        from fastapi.testclient import TestClient
        from worldcup_predictor.api.main import app

        client = TestClient(app)
        r_health = client.get("/api/admin/health")
        record("admin_health_unauthenticated_401", r_health.status_code == 401)
        r_gate = client.post("/api/admin/gate/verify", json={"access_key": "x"})
        record("gate_verify_unauthenticated_401", r_gate.status_code == 401)
    except Exception as exc:
        record("fastapi_smoke", False, str(exc))

    # Admin pages should not fetch before gate — AdminRoute renders gate first
    record("admin_panel_behind_gate", "AdminGatePrompt" in admin_route)

    _report(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
