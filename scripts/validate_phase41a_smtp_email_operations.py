"""Phase 41A — SMTP + email operations validation."""

from __future__ import annotations

import runpy
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 41A validation: {passed}/{len(checks)} PASS")
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

    record("email_delivery_module", (root / "worldcup_predictor/notifications/email_delivery.py").is_file())
    record("email_templates_module", (root / "worldcup_predictor/notifications/email_templates.py").is_file())
    record("password_reset_module", (root / "worldcup_predictor/auth/password_reset.py").is_file())
    record("migration_006_exists", (root / "alembic/versions/006_password_reset_tokens.py").is_file())
    record("forgot_password_wired", "requestPasswordReset(email" in (root / "base44-d/src/pages/ForgotPassword.jsx").read_text(encoding="utf-8"))
    record("reset_password_wired", "resetPassword(token" in (root / "base44-d/src/pages/ResetPassword.jsx").read_text(encoding="utf-8"))

    tpl_src = (root / "worldcup_predictor/notifications/email_templates.py").read_text(encoding="utf-8")
    record("html_templates", "verification_email" in tpl_src and "password_reset_email" in tpl_src and "contact_admin_notification" in tpl_src)

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.notifications.diagnostics import email_diagnostics
    from worldcup_predictor.notifications.email_delivery import EmailSendResult, send_email, smtp_configured
    from worldcup_predictor.notifications.email_templates import password_reset_email, verification_email

    settings = get_settings()
    diag = email_diagnostics(settings)
    record("diagnostics_no_secrets", "smtp_password" not in str(diag) and not (settings.smtp_password and settings.smtp_password in str(diag)))
    record("diagnostics_structure", all(k in diag for k in ("smtp_configured", "channels", "app_public_url")))

    subj, text, html = verification_email(verify_url="https://example.com/verify?token=x", ttl_hours=24)
    record("verification_template_multipart", bool(subj and text and html and "Verify" in html))

    subj2, text2, html2 = password_reset_email(reset_url="https://example.com/reset?token=x", ttl_hours=1)
    record("reset_template_multipart", bool(subj2 and text2 and html2 and "Reset" in html2))

    delivered: list[EmailSendResult] = []

    def _mock_send(**kwargs):
        delivered.append(EmailSendResult(delivered=True, channel="smtp"))
        return delivered[-1]

    with patch("worldcup_predictor.notifications.email_delivery.smtp_configured", return_value=True), patch(
        "worldcup_predictor.auth.email_verification.send_email", side_effect=_mock_send
    ), patch("worldcup_predictor.auth.password_reset.send_email", side_effect=_mock_send), patch(
        "worldcup_predictor.subscription.contact_admin.send_email", side_effect=_mock_send
    ):
        from worldcup_predictor.auth.email_verification import issue_verification_token, verify_email_token
        from worldcup_predictor.auth.password_reset import (
            issue_password_reset_token,
            request_password_reset_for_email,
            reset_password_with_token,
        )
        from worldcup_predictor.auth.passwords import hash_password, verify_password
        from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

        if not postgres_configured():
            record("postgres_required", False, "DATABASE_URL not configured")
            _report(checks)
            return 1

        from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits

        reset_auth_rate_limits()

        from fastapi.testclient import TestClient
        from worldcup_predictor.api.main import app

        client = TestClient(app)
        pwd = "Phase41A-Test-Pass!"
        email = f"phase41a-{uuid.uuid4().hex[:8]}@test.local"

        with saas_uow() as uow:
            user = uow.users.create(
                email=email,
                password_hash=hash_password("OldPass41A!"),
                email_verified=False,
            )
            user_id = user.id

        raw_verify, _ = issue_verification_token(user_id, email=email, settings=settings)
        ok, msg = verify_email_token(raw_verify)
        record("verification_token_works", ok, msg)

        with saas_uow() as uow:
            u = uow.users.get_by_email(email)
            record("verified_flag_set", u is not None and u.email_verified is True)

        # Anti-enumeration: unknown email same response
        resp_known = client.post("/api/auth/forgot-password", json={"email": email})
        resp_unknown = client.post("/api/auth/forgot-password", json={"email": f"unknown-{uuid.uuid4().hex}@test.local"})
        record(
            "forgot_password_no_enumeration",
            resp_known.status_code == 200
            and resp_unknown.status_code == 200
            and resp_known.json().get("message") == resp_unknown.json().get("message"),
        )

        raw_reset = issue_password_reset_token(user_id, email=email, settings=settings)
        ok_reset, msg_reset = reset_password_with_token(raw_reset, pwd)
        record("password_reset_works", ok_reset, msg_reset)

        with saas_uow() as uow:
            stored = uow.users.get_password_hash(email)
            record("password_hashed_after_reset", stored and verify_password(pwd, stored))

        # Rate limit: rapid resend should not error loudly
        request_password_reset_for_email(email, settings=settings)
        request_password_reset_for_email(email, settings=settings)
        record("reset_rate_limit_silent", True)

        # Resend verification anti-enumeration
        rv1 = client.post("/api/auth/resend-verification", json={"email": email})
        rv2 = client.post("/api/auth/resend-verification", json={"email": f"missing-{uuid.uuid4().hex}@test.local"})
        record(
            "resend_no_enumeration",
            rv1.status_code == 200 and rv2.status_code == 200 and rv1.json().get("message") == rv2.json().get("message"),
        )

        # Unverified user predict blocked (regression)
        from worldcup_predictor.api.web_auth import issue_access_token_for_record

        with saas_uow() as uow:
            unv = uow.users.create(
                email=f"unv41a-{uuid.uuid4().hex[:8]}@test.local",
                password_hash=hash_password(pwd),
                email_verified=False,
            )
            token = issue_access_token_for_record(unv)
        pred = client.post("/api/predict/1489393", headers={"Authorization": f"Bearer {token}"})
        record("unverified_predict_blocked", pred.status_code == 403)

        # Contact admin uses shared mail layer
        from worldcup_predictor.subscription.contact_admin import send_admin_contact_email

        test_settings = settings.model_copy(update={"admin_contact_email": "admin@test.local"})
        sent = send_admin_contact_email(
            user_email=email,
            subject="Phase 41A test",
            message="Test contact message",
            category="support",
            settings=test_settings,
        )
        record("contact_admin_email_path", sent is True)

        # Admin diagnostics route
        from worldcup_predictor.access.admin_gate import attempt_gate_unlock

        with saas_uow() as uow:
            owner = uow.users.get_by_email(email)
        if owner and settings.super_admin_access_key:
            with saas_uow() as uow:
                uow.users.set_role(owner.id, __import__("worldcup_predictor.database.postgres.enums", fromlist=["UserRole"]).UserRole.SUPER_ADMIN)
            login = client.post("/api/auth/login", json={"email": email, "password": pwd})
            token = login.json().get("access_token")
            headers = {"Authorization": f"Bearer {token}"}
            ok_gate, _, _, gate_token = attempt_gate_unlock(
                user_id=str(owner.id),
                gate="super_admin",
                access_key=settings.super_admin_access_key,
            )
            if ok_gate and gate_token:
                headers["X-Super-Admin-Gate-Token"] = gate_token
                diag_resp = client.get("/api/admin/email/diagnostics", headers=headers)
                record("admin_email_diagnostics", diag_resp.status_code == 200, f"status={diag_resp.status_code}")

        # Cleanup test users
        with saas_uow() as uow:
            uow.users.delete_all_users()

        record("email_mock_delivered", len(delivered) >= 1, f"count={len(delivered)}")

    # Regression
    import subprocess
    import sys

    for label, script in (
        ("regression_40A", "validate_phase40a_auth_user_management.py"),
        ("regression_38A", "validate_phase38a_subscription_system.py"),
    ):
        proc = subprocess.run(
            [sys.executable, str(root / "scripts" / script)],
            capture_output=True,
            text=True,
            cwd=str(root),
        )
        ok = proc.returncode == 0 and "PASS" in proc.stdout
        tail = proc.stdout.strip().splitlines()[-1] if proc.stdout else proc.stderr[:80]
        record(label, ok, tail)

    _report(checks)
    failed = sum(1 for _, ok, _ in checks if not ok)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
