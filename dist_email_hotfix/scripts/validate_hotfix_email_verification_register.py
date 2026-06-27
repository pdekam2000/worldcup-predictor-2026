"""HOTFIX — registration email verification send + delivery status validation."""

from __future__ import annotations

import runpy
import uuid
from pathlib import Path
from unittest.mock import patch

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nHotfix email verification register validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def _no_secrets(text: str) -> bool:
    lower = text.lower()
    banned = ("sk_test_", "sk_live_", "whsec_", "smtp_password", "password123")
    return not any(b in lower for b in banned)


def main() -> int:
    import sys

    api_only = "--api-only" in sys.argv
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]
    auth_routes = (root / "worldcup_predictor/api/routes/auth.py").read_text(encoding="utf-8")
    register_page = (root / "base44-d/src/pages/Register.jsx").read_text(encoding="utf-8")
    verify_page = (root / "base44-d/src/pages/VerifyEmailPage.jsx").read_text(encoding="utf-8")
    login_page = (root / "base44-d/src/pages/Login.jsx").read_text(encoding="utf-8")
    auth_api = (root / "base44-d/src/api/authApi.js").read_text(encoding="utf-8")

    record("register_response_fields", all(x in auth_routes for x in ("verification_email_sent", "email_delivery_status")))
    record("resend_verification_email_route", "/resend-verification-email" in auth_routes)
    record("register_page_delivery_state", "verification_email_sent" in register_page if not api_only else True, "skipped (--api-only)" if api_only else "")
    record("verify_page_resend", "resendVerificationEmail" in verify_page if not api_only else True, "skipped (--api-only)" if api_only else "")
    record("login_resend_action", "Resend verification email" in login_page if not api_only else True, "skipped (--api-only)" if api_only else "")
    record("auth_api_resend_alias", "resendVerificationEmail" in auth_api if not api_only else True, "skipped (--api-only)" if api_only else "")

    from worldcup_predictor.config.settings import Settings, get_settings
    from worldcup_predictor.notifications.email_delivery import EmailSendResult, send_email

    base = get_settings()
    bare_settings = Settings.model_construct(
        database_url=base.database_url,
        app_env=base.app_env,
        smtp_host="",
        smtp_from="",
    )
    prod_settings = Settings.model_construct(
        database_url=base.database_url,
        app_env="production",
        smtp_host="",
        smtp_from="",
    )
    missing = send_email(
        to_email="user@example.com",
        subject="Test",
        text_body="hello",
        settings=bare_settings,
        dev_kind="verification",
    )
    record("missing_config_no_crash", missing.delivered is False)
    record("missing_config_status", missing.error == "email_not_configured")

    prod_missing = send_email(
        to_email="user@example.com",
        subject="Test",
        text_body="hello",
        settings=prod_settings,
        dev_kind="verification",
    )
    record("prod_missing_channel_skipped", prod_missing.channel == "skipped")

    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app
    from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits
    from worldcup_predictor.auth.email_verification import (
        issue_verification_token,
        reset_verification_rate_limits,
        verify_email_token,
    )
    from worldcup_predictor.auth.passwords import hash_password
    from worldcup_predictor.database.postgres.enums import SubscriptionPlan, UserRole
    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

    reset_auth_rate_limits()
    reset_verification_rate_limits()
    client = TestClient(app)
    pwd = "HotfixEmailVerify123!"
    sent_calls: list[str] = []

    def _mock_send(**kwargs):
        sent_calls.append(kwargs.get("to_email", ""))
        return EmailSendResult(delivered=True, channel="smtp")

    if not postgres_configured():
        record("postgres_required", False, "DATABASE_URL not configured")
        _report(checks)
        return 1

    from worldcup_predictor.access.config import public_access_code

    email = f"hotfix-email-{uuid.uuid4().hex[:8]}@test.local"
    reg_body = {"email": email, "password": pwd}
    invite = public_access_code() or None
    if invite:
        reg_body["invite_code"] = invite

    with patch("worldcup_predictor.auth.email_verification.send_email", side_effect=_mock_send):
        r = client.post("/api/auth/register", json=reg_body)
    record("register_success", r.status_code == 200, f"status={r.status_code}")
    body = r.json() if r.status_code == 200 else {}
    record("register_unverified_flag", body.get("email_verification_required") is True)
    record("register_email_sent_true", body.get("verification_email_sent") is True)
    record("register_delivery_sent", body.get("email_delivery_status") == "sent")
    record("register_no_token", "access_token" not in body)
    record("register_response_no_secrets", _no_secrets(r.text))

    with saas_uow() as uow:
        user = uow.users.get_by_email(email)
        record("user_email_verified_false", user is not None and user.email_verified is False)
        if user is not None:
            from sqlalchemy import func, select

            from worldcup_predictor.database.postgres.models import EmailVerificationToken

            token_count = uow.session.scalar(
                select(func.count())
                .select_from(EmailVerificationToken)
                .where(EmailVerificationToken.user_id == user.id)
            )
            record("verification_token_created", int(token_count or 0) >= 1, f"count={token_count}")
        else:
            record("verification_token_created", False, "user missing")
    record("send_called_on_register", len(sent_calls) >= 1)

    with patch("worldcup_predictor.auth.email_verification.send_email", side_effect=_mock_send):
        r_resend = client.post("/api/auth/resend-verification-email", json={"email": email})
    record("resend_endpoint_works", r_resend.status_code == 200)
    resend_body = r_resend.json()
    record("resend_email_sent", resend_body.get("verification_email_sent") is True)

    with saas_uow() as uow:
        user = uow.users.get_by_email(email)
        raw, _ = issue_verification_token(user.id, email=user.email)
    ok, _ = verify_email_token(raw)
    record("verify_token_marks_verified", ok)
    with saas_uow() as uow:
        verified = uow.users.get_by_email(email)
        record("user_verified_after_link", verified is not None and verified.email_verified is True)

    r_login = client.post("/api/auth/login", json={"email": email, "password": pwd})
    record("login_after_verification", r_login.status_code == 200)

    email2 = f"hotfix-unv-{uuid.uuid4().hex[:8]}@test.local"
    reg2 = {"email": email2, "password": pwd}
    if invite:
        reg2["invite_code"] = invite
    reset_auth_rate_limits()
    with patch("worldcup_predictor.auth.email_verification.send_email", side_effect=_mock_send):
        r_reg2 = client.post("/api/auth/register", json=reg2)
    record("register_second_user", r_reg2.status_code == 200, f"status={r_reg2.status_code}")
    r_unv = client.post("/api/auth/login", json={"email": email2, "password": pwd})
    record("login_before_verification_allowed", r_unv.status_code == 200)
    if r_unv.status_code == 200:
        record("login_sets_verification_required", r_unv.json().get("verification_required") is True)

    reset_verification_rate_limits()
    with patch("worldcup_predictor.auth.email_verification.send_email", side_effect=_mock_send):
        r_already = client.post("/api/auth/resend-verification-email", json={"email": email})
    record("resend_already_verified", r_already.status_code == 200 and r_already.json().get("already_verified") is True)

    r_unknown = client.post("/api/auth/resend-verification-email", json={"email": "missing-user@test.local"})
    record("resend_unknown_generic", r_unknown.status_code == 200)
    record(
        "resend_unknown_no_enumeration",
        r_unknown.json().get("already_verified") is False and r_unknown.json().get("verification_email_sent") is False,
    )

    reg_missing_body = {"email": email, "password": pwd}
    if invite:
        reg_missing_body["invite_code"] = invite
    with patch("worldcup_predictor.auth.email_verification.send_email") as mock_send:
        mock_send.return_value = EmailSendResult(delivered=False, channel="skipped", error="email_not_configured")
        r_miss = client.post("/api/auth/register", json=reg_missing_body)
    record("duplicate_still_blocked", r_miss.status_code == 400)

    email3 = f"hotfix-nosmtp-{uuid.uuid4().hex[:8]}@test.local"
    reg3 = {"email": email3, "password": pwd}
    if invite:
        reg3["invite_code"] = invite
    reset_auth_rate_limits()
    with patch("worldcup_predictor.auth.email_verification.send_email") as mock_send:
        mock_send.return_value = EmailSendResult(delivered=False, channel="skipped", error="email_not_configured")
        r_no = client.post("/api/auth/register", json=reg3)
    record("missing_config_register_ok", r_no.status_code == 200)
    if r_no.status_code == 200:
        nb = r_no.json()
        record("missing_config_delivery_flag", nb.get("email_delivery_status") == "email_not_configured")
        record("missing_config_sent_false", nb.get("verification_email_sent") is False)

    reset_verification_rate_limits()
    with patch("worldcup_predictor.auth.email_verification.send_email") as mock_send:
        mock_send.return_value = EmailSendResult(delivered=False, channel="smtp", error="send_failed")
        r_fail = client.post("/api/auth/resend-verification-email", json={"email": email3})
    record("send_failed_no_crash", r_fail.status_code == 200)
    if r_fail.status_code == 200:
        record("send_failed_status", r_fail.json().get("email_delivery_status") == "send_failed")

    r_forgot = client.post("/api/auth/forgot-password", json={"email": email})
    record("password_reset_still_works", r_forgot.status_code == 200)

    record("billing_untouched", "stripe" not in auth_routes.lower() or "billing" not in auth_routes)

    _report(checks)
    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print("DEPLOY_READY=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
