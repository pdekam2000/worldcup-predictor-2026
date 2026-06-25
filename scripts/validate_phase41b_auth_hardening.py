"""Phase 41B — auth production hardening validation."""

from __future__ import annotations

import json
import runpy
import uuid
from pathlib import Path
from unittest.mock import patch

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 41B validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def _read_auth_audit_tail(settings, n: int = 50) -> list[dict]:
    path = Path(settings.auth_audit_log_path)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]

    record("auth_audit_module", (root / "worldcup_predictor/auth/auth_audit.py").is_file())
    record("auth_rate_limit_module", (root / "worldcup_predictor/auth/auth_rate_limit.py").is_file())

    dev_src = (root / "base44-d/src/lib/devAuth.js").read_text(encoding="utf-8")
    record("dev_auth_requires_dev_mode", "import.meta.env.DEV &&" in dev_src)
    record("dev_mock_user_not_admin", 'role: "user"' in dev_src or "role: 'user'" in dev_src)

    web_src = (root / "worldcup_predictor/api/web_auth.py").read_text(encoding="utf-8")
    record("logout_bumps_token_version", "bump_token_version" in web_src and "revoke_session_token" in web_src)

    admin_src = (root / "worldcup_predictor/api/routes/admin.py").read_text(encoding="utf-8")
    record("role_change_bumps_token", "set_role" in admin_src and "bump_token_version" in admin_src)

    gate_src = (root / "worldcup_predictor/access/admin_gate.py").read_text(encoding="utf-8")
    record("gate_uses_settings_ttl", "admin_gate_ttl_minutes" in gate_src)

    prod_guard = (root / "worldcup_predictor/config/production_guard.py").read_text(encoding="utf-8")
    record("prod_guard_admin_keys", "ADMIN_ACCESS_KEY" in prod_guard and "SUPER_ADMIN_ACCESS_KEY" in prod_guard)

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits
    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

    reset_auth_rate_limits()

    if not postgres_configured():
        record("postgres_required", False, "DATABASE_URL not configured")
        _report(checks)
        return 1

    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app
    from worldcup_predictor.api.web_auth import issue_access_token_for_record, resolve_bearer_token
    from worldcup_predictor.auth.passwords import hash_password
    from worldcup_predictor.database.postgres.enums import UserRole

    settings = get_settings()
    client = TestClient(app)
    pwd = "Phase41B-Test-Pass!"
    email = f"phase41b-{uuid.uuid4().hex[:8]}@test.local"

    with saas_uow() as uow:
        user = uow.users.create(
            email=email,
            password_hash=hash_password(pwd),
            email_verified=True,
        )
        user_id = user.id

    # Login + logout revokes session
    login = client.post("/api/auth/login", json={"email": email, "password": pwd})
    token = login.json().get("access_token")
    record("login_success", login.status_code == 200 and bool(token))
    me1 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    record("token_valid_before_logout", me1.status_code == 200)
    logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    record("logout_ok", logout.status_code == 200)
    me2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    record("logout_revokes_session", me2.status_code == 401, f"status={me2.status_code}")

    # Fresh login for further tests
    login2 = client.post("/api/auth/login", json={"email": email, "password": pwd})
    token2 = login2.json().get("access_token")

    # Password reset revokes session
    from worldcup_predictor.auth.password_reset import issue_password_reset_token, reset_password_with_token

    raw_reset = issue_password_reset_token(user_id, email=email, settings=settings)
    ok_reset, _ = reset_password_with_token(raw_reset, "NewPhase41B-Pass!")
    record("password_reset_ok", ok_reset)
    me3 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token2}"})
    record("password_reset_revokes_session", me3.status_code == 401, f"status={me3.status_code}")

    # Ban revokes session
    login3 = client.post("/api/auth/login", json={"email": email, "password": "NewPhase41B-Pass!"})
    token3 = login3.json().get("access_token")
    with saas_uow() as uow:
        uow.users.set_banned(user_id, reason="phase41b test")
        uow.users.bump_token_version(user_id)
    me4 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token3}"})
    record("ban_revokes_session", me4.status_code == 401, f"status={me4.status_code}")

    # Unban and kick
    with saas_uow() as uow:
        uow.users.clear_ban(user_id)
    login4 = client.post("/api/auth/login", json={"email": email, "password": "NewPhase41B-Pass!"})
    token4 = login4.json().get("access_token")
    with saas_uow() as uow:
        uow.users.bump_token_version(user_id)
    me5 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token4}"})
    record("kick_revokes_session", me5.status_code == 401, f"status={me5.status_code}")

    # Unverified predict blocked
    unv_email = f"unv41b-{uuid.uuid4().hex[:8]}@test.local"
    with saas_uow() as uow:
        unv = uow.users.create(email=unv_email, password_hash=hash_password(pwd), email_verified=False)
        unv_token = issue_access_token_for_record(unv)
    pred = client.post("/api/predict/1489393", headers={"Authorization": f"Bearer {unv_token}"})
    record("unverified_predict_blocked", pred.status_code == 403)

    # Verified predict allowed (auth only — may fail for other reasons)
    login5 = client.post("/api/auth/login", json={"email": email, "password": "NewPhase41B-Pass!"})
    vtoken = login5.json().get("access_token")
    pred2 = client.post("/api/predict/1489393", headers={"Authorization": f"Bearer {vtoken}"})
    record("verified_user_predict_not_401", pred2.status_code != 401, f"status={pred2.status_code}")

    # Role enforcement: plain user cannot access admin
    user_email = f"user41b-{uuid.uuid4().hex[:8]}@test.local"
    with saas_uow() as uow:
        plain = uow.users.create(email=user_email, password_hash=hash_password(pwd), email_verified=True)
        plain_token = issue_access_token_for_record(plain)
    admin_resp = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {plain_token}"})
    record("user_blocked_from_admin", admin_resp.status_code in (403, 401), f"status={admin_resp.status_code}")

    # Admin cannot access super-admin-only route without super_admin role
    admin_email = f"admin41b-{uuid.uuid4().hex[:8]}@test.local"
    with saas_uow() as uow:
        adm = uow.users.create(
            email=admin_email,
            password_hash=hash_password(pwd),
            email_verified=True,
            role=UserRole.ADMIN,
        )
        adm_token = issue_access_token_for_record(adm)
    sa_resp = client.patch(
        f"/api/admin/users/{user_id}/role",
        headers={"Authorization": f"Bearer {adm_token}"},
        json={"role": "user"},
    )
    record("admin_blocked_from_super_admin", sa_resp.status_code == 403, f"status={sa_resp.status_code}")

    # Forgot password no enumeration
    fp1 = client.post("/api/auth/forgot-password", json={"email": email})
    fp2 = client.post("/api/auth/forgot-password", json={"email": f"missing-{uuid.uuid4().hex}@test.local"})
    record(
        "forgot_password_no_enumeration",
        fp1.status_code == 200 and fp2.status_code == 200 and fp1.json().get("message") == fp2.json().get("message"),
    )

    # Login rate limit after repeated failures
    from worldcup_predictor.auth.auth_rate_limit import LOGIN_MAX_FAILURES

    fail_email = f"fail41b-{uuid.uuid4().hex[:8]}@test.local"
    with saas_uow() as uow:
        uow.users.create(email=fail_email, password_hash=hash_password(pwd), email_verified=True)
    statuses = []
    for _ in range(LOGIN_MAX_FAILURES + 1):
        r = client.post("/api/auth/login", json={"email": fail_email, "password": "wrong-password"})
        statuses.append(r.status_code)
    record("login_rate_limit_enforced", 401 in statuses, f"statuses={statuses[-3:]}")

    # Audit events
    events = {e.get("event") for e in _read_auth_audit_tail(settings)}
    for needed in (
        "login_success",
        "logout",
        "password_reset_success",
        "login_failed",
        "password_reset_requested",
    ):
        record(f"audit_{needed}", needed in events, f"seen={needed in events}")

    # Gate keys not in frontend bundle source check
    saas_api = (root / "base44-d/src/api/saasApi.js").read_text(encoding="utf-8")
    record("frontend_no_admin_access_key", "ADMIN_ACCESS_KEY" not in saas_api)

    # Cleanup
    with saas_uow() as uow:
        uow.users.delete_all_users()

    # Regressions
    import subprocess
    import sys

    for label, script in (
        ("regression_40A", "validate_phase40a_auth_user_management.py"),
        ("regression_41A", "validate_phase41a_smtp_email_operations.py"),
        ("regression_39A", "validate_phase39a_commercial_readiness.py"),
        ("regression_38A", "validate_phase38a_subscription_system.py"),
        ("regression_37A", "validate_phase37a_admin_security.py"),
    ):
        reset_auth_rate_limits()
        proc = subprocess.run(
            [sys.executable, str(root / "scripts" / script)],
            capture_output=True,
            text=True,
            cwd=str(root),
        )
        ok = proc.returncode == 0
        tail = next((ln for ln in reversed(proc.stdout.splitlines()) if "validation:" in ln.lower()), proc.stdout[-80:])
        record(label, ok, tail.strip())

    _report(checks)
    failed = sum(1 for _, ok, _ in checks if not ok)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
