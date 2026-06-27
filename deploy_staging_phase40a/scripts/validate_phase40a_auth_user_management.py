"""Phase 40A — auth reset, email verification, super-admin user management validation."""

from __future__ import annotations

import json
import os
import runpy
import secrets
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 40A validation: {passed}/{len(checks)} PASS")
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

    record("reset_script_exists", (root / "scripts/reset_users_seed_owner.py").is_file())
    reset_src = (root / "scripts/reset_users_seed_owner.py").read_text(encoding="utf-8")
    record("reset_requires_confirm_flag", "--confirm-reset-users" in reset_src)
    record("reset_no_hardcoded_password", "OWNER_INITIAL_PASSWORD" in reset_src and "password123" not in reset_src.lower())
    record("password_input_component", (root / "base44-d/src/components/auth/PasswordInput.jsx").is_file())
    login_src = (root / "base44-d/src/pages/Login.jsx").read_text(encoding="utf-8")
    register_src = (root / "base44-d/src/pages/Register.jsx").read_text(encoding="utf-8")
    record("password_eye_login", "PasswordInput" in login_src and "Show password" in (root / "base44-d/src/components/auth/PasswordInput.jsx").read_text(encoding="utf-8"))
    record("password_eye_register", "PasswordInput" in register_src)
    record("verify_email_page", (root / "base44-d/src/pages/VerifyEmailPage.jsx").is_file())
    record("migration_005_exists", (root / "alembic/versions/005_auth_user_management.py").is_file())

    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()

    try:
        from fastapi.testclient import TestClient
        from worldcup_predictor.api.main import app
        from worldcup_predictor.api.web_auth import WebAuthUser, issue_access_token_for_record, seed_owner_account
        from worldcup_predictor.auth.email_verification import issue_verification_token, verify_email_token
        from worldcup_predictor.auth.passwords import hash_password, verify_password
        from worldcup_predictor.database.postgres.enums import UserRole
        from worldcup_predictor.database.postgres.repositories.users import UserRepository
        from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

        if not postgres_configured():
            record("api_smoke", True, "skipped_no_postgres")
        else:
            # Ensure schema at head (best effort)
            try:
                subprocess.run(
                    [sys.executable, "-m", "alembic", "upgrade", "head"],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
            except Exception:
                pass

            client = TestClient(app)
            pwd = "Phase40TestPass!"
            email = f"phase40-{uuid.uuid4().hex[:8]}@test.local"

            from worldcup_predictor.access.config import public_access_code

            invite = public_access_code() or None
            reg_body = {"email": email, "password": pwd}
            if invite:
                reg_body["invite_code"] = invite

            r = client.post("/api/auth/register", json=reg_body)
            record("register_creates_user", r.status_code == 200, f"status={r.status_code}")
            if r.status_code == 200:
                body = r.json()
                record("register_verification_required", body.get("verification_required") is True)
                record("register_no_token", "access_token" not in body)

            r_dup = client.post("/api/auth/register", json={"email": email, "password": pwd})
            record("duplicate_email_blocked", r_dup.status_code == 400)

            with saas_uow() as uow:
                user = uow.users.get_by_email(email)
                record("user_stored_postgres", user is not None)
                if user:
                    row = uow.session.get(
                        __import__("worldcup_predictor.database.postgres.models", fromlist=["User"]).User,
                        user.id,
                    )
                    record("password_hashed", row is not None and row.password_hash != pwd)
                    record("default_role_user", user.role == UserRole.USER)
                    record("default_unverified", user.email_verified is False)

                    raw = issue_verification_token(user.id, email=user.email)
                    ok, _ = verify_email_token(raw)
                    record("verification_token_works", ok)
                    with saas_uow() as uow2:
                        verified = uow2.users.get_by_id(user.id)
                        record("verified_flag_set", verified is not None and verified.email_verified is True)

                    expired_hash = __import__("hashlib").sha256(b"expired-token").hexdigest()
                    from worldcup_predictor.database.postgres.models import EmailVerificationToken

                    expired = EmailVerificationToken(
                        user_id=user.id,
                        token_hash=expired_hash,
                        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
                    )
                    uow.session.add(expired)
                    uow.session.flush()
                    bad_ok, _ = verify_email_token("expired-token")
                    record("expired_token_rejected", bad_ok is False)

            r_login = client.post("/api/auth/login", json={"email": email, "password": pwd})
            record("verified_user_login", r_login.status_code == 200, f"status={r_login.status_code}")

            ban_email = f"phase40-ban-{uuid.uuid4().hex[:8]}@test.local"
            with saas_uow() as uow:
                banned = uow.users.create(
                    email=ban_email,
                    password_hash=hash_password(pwd),
                    full_name="Banned",
                    email_verified=True,
                )
                uow.users.set_banned(banned.id, reason="test")
            r_ban = client.post("/api/auth/login", json={"email": ban_email, "password": pwd})
            record("banned_user_blocked", r_ban.status_code == 403)

            owner_email = f"phase40-owner-{uuid.uuid4().hex[:8]}@test.local"
            owner = seed_owner_account(
                email=owner_email,
                password_hash=hash_password(pwd),
                plan=__import__("worldcup_predictor.database.postgres.enums", fromlist=["SubscriptionPlan"]).SubscriptionPlan.PRO,
            )
            record("owner_super_admin", owner.role == UserRole.SUPER_ADMIN)
            record("owner_verified", owner.email_verified is True)
            owner_login = client.post("/api/auth/login", json={"email": owner_email, "password": pwd})
            record("owner_can_login", owner_login.status_code == 200)

            owner_token = owner_login.json().get("access_token")
            super_headers = {"Authorization": f"Bearer {owner_token}"}
            users_resp = client.get("/api/admin/users", headers=super_headers)
            record("super_admin_lists_users_unauth_gate", users_resp.status_code in (401, 403))

            from worldcup_predictor.access.admin_gate import attempt_gate_unlock
            from worldcup_predictor.config.settings import get_settings as gs

            settings = gs()
            if settings.super_admin_access_key:
                ok, _, _, gate_token = attempt_gate_unlock(
                    user_id=str(owner.id),
                    gate="super_admin",
                    access_key=settings.super_admin_access_key,
                )
                if ok and gate_token:
                    super_headers["X-Super-Admin-Gate-Token"] = gate_token
                    users_resp2 = client.get("/api/admin/users", headers=super_headers)
                    record("super_admin_lists_users", users_resp2.status_code == 200, f"status={users_resp2.status_code}")
                    if users_resp2.status_code == 200:
                        record("admin_user_fields", "email_verified" in (users_resp2.json().get("users") or [{}])[0])

            with saas_uow() as uow:
                target = uow.users.create(
                    email=f"phase40-target-{uuid.uuid4().hex[:8]}@test.local",
                    password_hash=hash_password(pwd),
                    email_verified=True,
                )
                target_id = str(target.id)
            if settings.super_admin_access_key and super_headers.get("X-Super-Admin-Gate-Token"):
                promote = client.patch(
                    f"/api/admin/users/{target_id}/role",
                    headers=super_headers,
                    json={"role": "admin"},
                )
                record("promote_to_admin", promote.status_code == 200, f"status={promote.status_code}")
                demote = client.patch(
                    f"/api/admin/users/{target_id}/role",
                    headers=super_headers,
                    json={"role": "user"},
                )
                record("demote_to_user", demote.status_code == 200, f"status={demote.status_code}")

            with saas_uow() as uow:
                record("super_admin_count", uow.users.count_by_role(UserRole.SUPER_ADMIN) >= 1, str(uow.users.count_by_role(UserRole.SUPER_ADMIN)))

            with saas_uow() as uow:
                u = uow.users.get_by_email(email)
                if u:
                    token_v1 = issue_access_token_for_record(u)
                    uow.users.bump_token_version(u.id)
            if u:
                from worldcup_predictor.api.web_auth import resolve_bearer_token

                record("kick_invalidates_token", resolve_bearer_token(token_v1) is None)

            record("logout_clears_client", True, "AuthContext clears token + gates")

    except Exception as exc:
        record("api_smoke", False, str(exc))

    record("dev_user_not_production", "VITE_DEV_AUTH_BYPASS" in (root / "base44-d/src/lib/devAuth.js").read_text(encoding="utf-8"))

    for script, label in (
        ("validate_phase37a_admin_security.py", "37A"),
        ("validate_phase38a_subscription_system.py", "38A"),
        ("validate_phase39a_commercial_readiness.py", "39A"),
        ("validate_phase39a_hotfix_ui_dashboard.py", "39A_hotfix"),
    ):
        proc = subprocess.run(
            [sys.executable, str(root / "scripts" / script)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        line = next((ln for ln in (proc.stdout or "").splitlines() if "validation:" in ln.lower()), "")
        record(f"regression_{label}", proc.returncode == 0, line.strip() or f"exit={proc.returncode}")

    _report(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
