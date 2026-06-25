"""Phase 41D — change password in settings validation."""

from __future__ import annotations

import io
import json
import runpy
import uuid
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 41D validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def _detail_code(response) -> str | None:
    detail = response.json().get("detail")
    if isinstance(detail, dict):
        return detail.get("code")
    return None


def _change_password(client, token: str, body: dict):
    return client.post(
        "/api/auth/change-password",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )


def _frontend_bundle_text(root: Path) -> str:
    dist = root / "base44-d" / "dist" / "assets"
    if not dist.is_dir():
        dist = Path("/var/www/worldcup/frontend/dist/assets")
    if not dist.is_dir():
        return ""
    parts = []
    for js in dist.glob("index-*.js"):
        try:
            parts.append(js.read_text(encoding="utf-8", errors="ignore")[:500000])
        except OSError:
            continue
    return "\n".join(parts)


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]
    record("change_password_module", (root / "worldcup_predictor/auth/change_password.py").is_file())
    record("auth_route_has_endpoint", "/change-password" in (root / "worldcup_predictor/api/routes/auth.py").read_text(encoding="utf-8"))
    record("settings_page_change_password", "Change Password" in (root / "base44-d/src/pages/SettingsPage.jsx").read_text(encoding="utf-8"))
    auth_src = root / "base44-d/src/api/authApi.js"
    bundle = _frontend_bundle_text(root)
    record(
        "auth_api_change_password",
        ("changePassword" in auth_src.read_text(encoding="utf-8") if auth_src.is_file() else False)
        or "change-password" in bundle,
    )

    from worldcup_predictor.auth.passwords import hash_password, verify_password
    from worldcup_predictor.api.web_auth import login_with_password, resolve_bearer_token
    from worldcup_predictor.database.postgres.enums import UserRole
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

    user_email = f"phase41d-user-{uuid.uuid4().hex[:8]}@test.local"
    admin_email = f"phase41d-admin-{uuid.uuid4().hex[:8]}@test.local"
    old_password = "Phase41D-Old-Pass!"
    new_password = "Phase41D-New-Pass!"
    weak_password = "short"
    wrong_password = "Phase41D-Wrong-Pass!"

    with saas_uow() as uow:
        user = uow.users.create(
            email=user_email,
            password_hash=hash_password(old_password),
            email_verified=True,
        )
        user_id = user.id
        user_tv = user.token_version

        admin = uow.users.create(
            email=admin_email,
            password_hash=hash_password(old_password),
            email_verified=True,
            role=UserRole.SUPER_ADMIN,
        )
        admin_id = admin.id

    login_user = client.post("/api/auth/login", json={"email": user_email, "password": old_password})
    user_token = login_user.json().get("access_token")
    record("user_login_ok", login_user.status_code == 200 and bool(user_token))

    login_admin = client.post("/api/auth/login", json={"email": admin_email, "password": old_password})
    admin_token = login_admin.json().get("access_token")
    record("admin_login_ok", login_admin.status_code == 200 and bool(admin_token))

    unauth = client.post(
        "/api/auth/change-password",
        json={
            "current_password": old_password,
            "new_password": new_password,
            "confirm_password": new_password,
        },
    )
    record("unauthenticated_rejected", unauth.status_code == 401, f"status={unauth.status_code}")

    wrong_current = _change_password(
        client,
        user_token,
        {
            "current_password": wrong_password,
            "new_password": new_password,
            "confirm_password": new_password,
        },
    )
    record(
        "wrong_current_password_fails",
        wrong_current.status_code == 400 and _detail_code(wrong_current) == "current_password_invalid",
        _detail_code(wrong_current) or "",
    )

    mismatch = _change_password(
        client,
        user_token,
        {
            "current_password": old_password,
            "new_password": new_password,
            "confirm_password": "Phase41D-Mismatch!",
        },
    )
    record(
        "confirm_mismatch_fails",
        mismatch.status_code == 400 and _detail_code(mismatch) == "password_mismatch",
        _detail_code(mismatch) or "",
    )

    weak = _change_password(
        client,
        user_token,
        {
            "current_password": old_password,
            "new_password": weak_password,
            "confirm_password": weak_password,
        },
    )
    record(
        "weak_password_fails",
        weak.status_code == 400 and _detail_code(weak) == "password_too_weak",
        _detail_code(weak) or "",
    )

    same = _change_password(
        client,
        user_token,
        {
            "current_password": old_password,
            "new_password": old_password,
            "confirm_password": old_password,
        },
    )
    record(
        "same_password_fails",
        same.status_code == 400 and _detail_code(same) == "password_same_as_old",
        _detail_code(same) or "",
    )

    # Capture stdout/stderr — no password leak
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        ok_change = _change_password(
            client,
            user_token,
            {
                "current_password": old_password,
                "new_password": new_password,
                "confirm_password": new_password,
            },
        )
    combined = buf_out.getvalue() + buf_err.getvalue()
    record(
        "no_password_in_logs",
        old_password not in combined
        and new_password not in combined
        and wrong_password not in combined,
    )
    record(
        "user_change_success",
        ok_change.status_code == 200 and ok_change.json().get("password_changed") is True,
        f"status={ok_change.status_code}",
    )

    with saas_uow() as uow:
        updated_user = uow.users.get_by_id(user_id)
        user_hash = uow.users.get_password_hash(user_email)
        admin_hash_before = uow.users.get_password_hash(admin_email)

    record("token_version_incremented", updated_user is not None and updated_user.token_version == user_tv + 1)
    record("new_password_verifies", verify_password(new_password, user_hash or ""))
    record("old_password_rejected", not verify_password(old_password, user_hash or ""))

    record("old_token_invalidated", resolve_bearer_token(user_token) is None)
    me_old = client.get("/api/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    record("old_jwt_me_401", me_old.status_code == 401, f"status={me_old.status_code}")

    reset_auth_rate_limits()
    login_new = client.post("/api/auth/login", json={"email": user_email, "password": new_password})
    record("new_password_login_works", login_new.status_code == 200, f"status={login_new.status_code}")

    # Admin changes own password — normal user's hash must stay unchanged
    user_hash_before_admin = user_hash
    _change_password(
        client,
        admin_token,
        {
            "current_password": old_password,
            "new_password": "Phase41D-Admin-New!",
            "confirm_password": "Phase41D-Admin-New!",
        },
    )
    with saas_uow() as uow:
        admin_hash_after = uow.users.get_password_hash(admin_email)
        user_hash_after_admin = uow.users.get_password_hash(user_email)

    record(
        "cannot_change_other_user",
        user_hash_after_admin == user_hash_before_admin,
        "other user hash unchanged",
    )

    record(
        "super_admin_change_success",
        verify_password("Phase41D-Admin-New!", admin_hash_after or ""),
    )

    # Audit log must not contain passwords
    from worldcup_predictor.config.settings import get_settings

    audit_path = Path(get_settings().auth_audit_log_path)
    if audit_path.is_file():
        tail = audit_path.read_text(encoding="utf-8")[-8000:]
        record(
            "audit_log_no_passwords",
            old_password not in tail and new_password not in tail,
        )
    else:
        record("audit_log_no_passwords", True, "no audit file yet")

    _report(checks)
    failed = [name for name, ok, _ in checks if not ok]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
