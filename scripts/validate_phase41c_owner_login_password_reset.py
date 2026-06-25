"""Phase 41C — owner login password reset validation."""

from __future__ import annotations

import io
import os
import runpy
import subprocess
import sys
import uuid
from contextlib import redirect_stdout
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 41C validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]
    reset_script = root / "scripts" / "reset_owner_login_password.py"
    record("reset_script_exists", reset_script.is_file())

    from worldcup_predictor.auth.passwords import hash_password, verify_password
    from worldcup_predictor.auth.jwt_tokens import decode_access_token
    from worldcup_predictor.api.web_auth import login_with_password, resolve_bearer_token
    from worldcup_predictor.database.postgres.enums import SubscriptionPlan, UserRole
    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

    if not postgres_configured():
        record("postgres_required", False, "DATABASE_URL not configured")
        _report(checks)
        return 1

    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app
    from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits

    reset_auth_rate_limits()
    client = TestClient(app)

    owner_email = "kamangar.pedram@gmail.com"
    test_email = f"phase41c-{uuid.uuid4().hex[:8]}@test.local"
    old_password = "Phase41C-Old-Pass!"
    new_password = "Phase41C-New-Pass!"
    wrong_password = "Phase41C-Wrong-Pass!"

    owner_old_hash: str | None = None
    owner_id = None
    with saas_uow() as uow:
        owner = uow.users.get_by_email(owner_email)
        if owner is not None:
            owner_id = owner.id
            owner_old_hash = uow.users.get_password_hash(owner_email)
            record("owner_exists", True, owner_email)
            record(
                "owner_role_super_admin",
                owner.role == UserRole.SUPER_ADMIN,
                owner.role.value,
            )
            record("owner_email_verified", owner.email_verified is True)
        else:
            record("owner_exists", os.environ.get("PHASE41C_REQUIRE_OWNER") != "1", "not in DB (set PHASE41C_REQUIRE_OWNER=1 to enforce)")
            record("owner_role_super_admin", True, "skipped")
            record("owner_email_verified", True, "skipped")

        user = uow.users.create(
            email=test_email,
            password_hash=hash_password(old_password),
            full_name="Phase41C Test",
            role=UserRole.SUPER_ADMIN,
            email_verified=True,
        )
        user_id = user.id
        old_hash = uow.users.get_password_hash(test_email)
        old_tv = user.token_version
        uow.subscriptions.upsert(user_id, plan=SubscriptionPlan.PRO)

    # Issue token before reset (for invalidation test)
    login_before = client.post("/api/auth/login", json={"email": test_email, "password": old_password})
    old_token = login_before.json().get("access_token") if login_before.status_code == 200 else None
    record("pre_reset_login_ok", login_before.status_code == 200 and bool(old_token))

    # Run reset script against test user
    env = os.environ.copy()
    env["PHASE41C_TEST_PASSWORD"] = new_password
    proc = subprocess.run(
        [
            sys.executable,
            str(reset_script),
            "--email",
            test_email,
            "--password-env",
            "PHASE41C_TEST_PASSWORD",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(root),
    )
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    record("reset_script_exit_ok", proc.returncode == 0, stderr or f"rc={proc.returncode}")
    record("reset_script_password_reset_ok", "PASSWORD_RESET_OK" in stdout)
    record(
        "reset_script_no_password_leak",
        new_password not in stdout and new_password not in stderr and old_password not in stdout,
    )

    with saas_uow() as uow:
        new_hash = uow.users.get_password_hash(test_email)
        updated = uow.users.get_by_id(user_id)
        sub = uow.subscriptions.get_for_user(user_id)

    record("password_hash_changed", bool(new_hash) and new_hash != old_hash)
    record(
        "password_hash_verifies_new",
        bool(new_hash) and verify_password(new_password, new_hash),
    )
    record(
        "password_hash_rejects_old",
        bool(new_hash) and not verify_password(old_password, new_hash),
    )
    record("token_version_bumped", updated is not None and updated.token_version == old_tv + 1)
    record("super_admin_role_preserved", updated is not None and updated.role == UserRole.SUPER_ADMIN)
    record("email_verified_true", updated is not None and updated.email_verified is True)
    record("is_active_true", updated is not None and updated.is_active is True)
    record("is_banned_false", updated is not None and updated.is_banned is False)
    record("pro_plan_preserved", sub is not None and sub.plan == SubscriptionPlan.PRO)

    profile, error, code = login_with_password(email=test_email, password=new_password)
    record("login_with_password_success", profile is not None and error is None, error or "")
    record("login_wrong_password_fails", login_with_password(email=test_email, password=wrong_password)[0] is None)

    reset_auth_rate_limits()
    api_login = client.post("/api/auth/login", json={"email": test_email, "password": new_password})
    jwt = api_login.json().get("access_token") if api_login.status_code == 200 else None
    record("login_endpoint_returns_jwt", api_login.status_code == 200 and bool(jwt))

    if jwt:
        payload = decode_access_token(jwt)
        record("jwt_has_sub", bool(payload.get("sub")))
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {jwt}"})
        me_role = (me.json().get("user") or {}).get("role") if me.status_code == 200 else None
        record("jwt_me_ok", me.status_code == 200 and me_role == "super_admin", f"role={me_role}")

    if old_token:
        record("old_token_invalid_after_reset", resolve_bearer_token(old_token) is None)
        me_old = client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
        record("old_jwt_me_401", me_old.status_code == 401, f"status={me_old.status_code}")

    # Direct function path (no subprocess) for owner email when present
    if owner is not None and owner_id is not None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("reset_owner_login_password", reset_script)
        reset_mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(reset_mod)

        buf = io.StringIO()
        with redirect_stdout(buf):
            reset_mod.reset_owner_password(email=owner_email, password=new_password)
        out = buf.getvalue()
        record("owner_direct_reset_ok", "PASSWORD_RESET_OK" in out)
        record("owner_reset_no_password_leak", new_password not in out)

        reset_auth_rate_limits()
        owner_profile, owner_err, _ = login_with_password(email=owner_email, password=new_password)
        record("owner_login_with_password", owner_profile is not None and owner_err is None, owner_err or "")

        owner_api = client.post("/api/auth/login", json={"email": owner_email, "password": new_password})
        record(
            "owner_login_endpoint_jwt",
            owner_api.status_code == 200 and bool(owner_api.json().get("access_token")),
        )

        if owner_old_hash:
            with saas_uow() as uow:
                uow.users.update_password_hash(owner_id, owner_old_hash)
                uow.users.bump_token_version(owner_id)

    missing_email = f"phase41c-missing-{uuid.uuid4().hex[:8]}@test.local"
    env_create = os.environ.copy()
    env_create["PHASE41C_CREATE_PASSWORD"] = new_password
    create_proc = subprocess.run(
        [
            sys.executable,
            str(reset_script),
            "--email",
            missing_email,
            "--password-env",
            "PHASE41C_CREATE_PASSWORD",
        ],
        capture_output=True,
        text=True,
        env=env_create,
        cwd=str(root),
    )
    record("create_if_missing_ok", create_proc.returncode == 0 and "PASSWORD_RESET_OK" in create_proc.stdout)
    with saas_uow() as uow:
        created = uow.users.get_by_email(missing_email)
    record("created_user_super_admin", created is not None and created.role == UserRole.SUPER_ADMIN)

    _report(checks)
    failed = [name for name, ok, _ in checks if not ok]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
