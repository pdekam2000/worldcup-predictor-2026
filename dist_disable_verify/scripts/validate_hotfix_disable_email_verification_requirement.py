"""HOTFIX — temporarily disable email verification requirement validation."""

from __future__ import annotations

import runpy
import uuid
from pathlib import Path
from unittest.mock import patch

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nHotfix disable email verification validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def main() -> int:
    import sys

    api_only = "--api-only" in sys.argv
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]
    settings_src = (root / "worldcup_predictor/config/settings.py").read_text(encoding="utf-8")
    auth_routes = (root / "worldcup_predictor/api/routes/auth.py").read_text(encoding="utf-8")
    register_page = (root / "base44-d/src/pages/Register.jsx").read_text(encoding="utf-8")
    login_page = (root / "base44-d/src/pages/Login.jsx").read_text(encoding="utf-8")

    record("settings_flag", "EMAIL_VERIFICATION_REQUIRED" in settings_src)
    record("verification_config_module", (root / "worldcup_predictor/auth/verification_config.py").is_file())
    record("auth_config_endpoint", '"/config"' in auth_routes or '"/config"' in auth_routes)
    record("register_verification_disabled_message", "verification_disabled" in auth_routes)
    record("register_page_login_redirect", "You can now log in" in register_page if not api_only else True, "skipped (--api-only)" if api_only else "")
    record("login_hides_resend_when_disabled", "verificationRequired" in login_page if not api_only else True, "skipped (--api-only)" if api_only else "")

    from worldcup_predictor.config.settings import Settings, get_settings
    from worldcup_predictor.auth.verification_config import email_verification_required

    base = get_settings()
    disabled_settings = Settings.model_construct(
        database_url=base.database_url,
        app_env=base.app_env,
        email_verification_required=False,
    )
    enabled_settings = Settings.model_construct(
        database_url=base.database_url,
        app_env=base.app_env,
        email_verification_required=True,
    )
    record("flag_false", email_verification_required(disabled_settings) is False)
    record("flag_true_default", email_verification_required(enabled_settings) is True)

    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app
    from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits
    from worldcup_predictor.auth.email_verification import reset_verification_rate_limits
    from worldcup_predictor.auth.passwords import hash_password
    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

    if not postgres_configured():
        record("postgres_required", False, "DATABASE_URL not configured")
        _report(checks)
        return 1

    reset_auth_rate_limits()
    reset_verification_rate_limits()
    client = TestClient(app)
    pwd = "HotfixDisableVerify123!"
    sent_calls: list[str] = []

    def _mock_send(**kwargs):
        sent_calls.append(kwargs.get("to_email", ""))
        from worldcup_predictor.notifications.email_delivery import EmailSendResult

        return EmailSendResult(delivered=True, channel="smtp")

    from worldcup_predictor.access.config import public_access_code

    invite = public_access_code() or None

    with patch("worldcup_predictor.auth.verification_config.get_settings", return_value=disabled_settings):
        r_cfg = client.get("/api/auth/config")
        record("config_endpoint_disabled", r_cfg.status_code == 200 and r_cfg.json().get("email_verification_required") is False)

        email = f"hotfix-disabled-{uuid.uuid4().hex[:8]}@test.local"
        body = {"email": email, "password": pwd}
        if invite:
            body["invite_code"] = invite
        sent_calls.clear()
        with patch("worldcup_predictor.auth.email_verification.send_email", side_effect=_mock_send):
            r_reg = client.post("/api/auth/register", json=body)
        record("disabled_register_ok", r_reg.status_code == 200, f"status={r_reg.status_code}")
        if r_reg.status_code == 200:
            jb = r_reg.json()
            record("disabled_verification_not_required", jb.get("email_verification_required") is False)
            record("disabled_delivery_status", jb.get("email_delivery_status") == "verification_disabled")
            record("disabled_login_ready_message", "You can now log in" in (jb.get("message") or ""))
        record("disabled_no_email_send", len(sent_calls) == 0, f"calls={len(sent_calls)}")

        with saas_uow() as uow:
            user = uow.users.get_by_email(email)
            record("disabled_user_verified", user is not None and user.email_verified is True)

        r_login = client.post("/api/auth/login", json={"email": email, "password": pwd})
        record("disabled_login_immediate", r_login.status_code == 200)
        if r_login.status_code == 200:
            record("disabled_no_verification_flag", r_login.json().get("verification_required") is not True)
            record("disabled_jwt_issued", bool(r_login.json().get("access_token")))

    with patch("worldcup_predictor.auth.verification_config.get_settings", return_value=enabled_settings):
        r_cfg_on = client.get("/api/auth/config")
        record("config_endpoint_enabled", r_cfg_on.status_code == 200 and r_cfg_on.json().get("email_verification_required") is True)

        reset_auth_rate_limits()
        email_on = f"hotfix-enabled-{uuid.uuid4().hex[:8]}@test.local"
        body_on = {"email": email_on, "password": pwd}
        if invite:
            body_on["invite_code"] = invite
        sent_calls.clear()
        with patch("worldcup_predictor.auth.email_verification.send_email", side_effect=_mock_send):
            r_reg_on = client.post("/api/auth/register", json=body_on)
        record("enabled_register_ok", r_reg_on.status_code == 200)
        if r_reg_on.status_code == 200:
            jb_on = r_reg_on.json()
            record("enabled_verification_required", jb_on.get("email_verification_required") is True)
        record("enabled_email_send_attempted", len(sent_calls) >= 1)

        with saas_uow() as uow:
            user_on = uow.users.get_by_email(email_on)
            record("enabled_user_unverified", user_on is not None and user_on.email_verified is False)

        r_unv_login = client.post("/api/auth/login", json={"email": email_on, "password": pwd})
        record("enabled_unverified_login_allowed", r_unv_login.status_code == 200)
        if r_unv_login.status_code == 200:
            record("enabled_sets_verification_required", r_unv_login.json().get("verification_required") is True)

        reset_verification_rate_limits()
        with patch("worldcup_predictor.auth.email_verification.send_email", side_effect=_mock_send):
            r_resend = client.post("/api/auth/resend-verification-email", json={"email": email_on})
        record("enabled_resend_works", r_resend.status_code == 200)

    r_forgot = client.post("/api/auth/forgot-password", json={"email": email})
    record("password_reset_still_works", r_forgot.status_code == 200)

    record("prediction_engine_untouched", "weighted_decision" not in auth_routes)

    _report(checks)
    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print("DEPLOY_READY=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
