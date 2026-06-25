"""Phase 39B-4 — billing dashboard + customer portal validation."""

from __future__ import annotations

import json
import runpy
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 39B-4 validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def _no_secrets(text: str) -> bool:
    lower = text.lower()
    banned = ("sk_test_", "sk_live_", "whsec_", "price_1", "cs_test_", "cs_live_", "cus_")
    return not any(b in lower for b in banned)


def _test_settings():
    from worldcup_predictor.config.settings import Settings, get_settings

    base = get_settings()
    return Settings.model_construct(
        database_url=base.database_url,
        app_env=base.app_env,
        stripe_secret_key="sk_test_placeholder",
        stripe_webhook_secret="whsec_test_phase39b4",
        stripe_starter_price_id="price_starter_test",
        stripe_pro_price_id="price_pro_test",
        stripe_success_url="https://example.com/billing/success",
        stripe_cancel_url="https://example.com/billing/cancel",
        stripe_portal_return_url="https://example.com/subscription",
        stripe_mode="test",
    )


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]
    billing_routes = (root / "worldcup_predictor/api/routes/billing.py").read_text(encoding="utf-8")
    record("billing_status_route", '"/status"' in billing_routes)
    record("billing_history_route", '"/history"' in billing_routes)
    record("customer_portal_route", "customer-portal" in billing_routes)

    sub_page = (root / "base44-d/src/pages/SubscriptionPage.jsx").read_text(encoding="utf-8")
    record("frontend_fetchBillingStatus", "fetchBillingStatus" in sub_page)
    record("frontend_manage_subscription", "Manage subscription" in sub_page or "handleManageSubscription" in sub_page)
    record("frontend_checkout_pending", "checkout_pending" in sub_page or "checkoutPending" in sub_page)

    saas_api = (root / "base44-d/src/api/saasApi.js").read_text(encoding="utf-8")
    record("saasApi_billing_methods", all(x in saas_api for x in ("fetchBillingStatus", "fetchBillingHistory", "createCustomerPortalSession")))

    admin_panel = (root / "base44-d/src/pages/SuperAdminPanel.jsx").read_text(encoding="utf-8")
    record("super_admin_billing_view", "fetchAdminUserBilling" in admin_panel)

    from worldcup_predictor.billing.billing_service import BillingService
    from worldcup_predictor.database.postgres.enums import SubscriptionPlan, SubscriptionStatus
    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

    if not postgres_configured():
        record("postgres_required", False, "DATABASE_URL not configured")
        _report(checks)
        return 1

    test_settings = _test_settings()
    mock_client = MagicMock()
    mock_client.package_available = True
    mock_client.sdk_ready.return_value = True
    mock_client.create_portal_session.return_value = "https://billing.stripe.test/portal/session"

    svc = BillingService(settings=test_settings, client=mock_client)
    ready = svc.readiness()
    record("portal_enabled_readiness", ready.portal_enabled is True)

    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app
    from worldcup_predictor.api.web_auth import issue_access_token_for_record
    from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits
    from worldcup_predictor.auth.passwords import hash_password
    from worldcup_predictor.billing.checkout_rate_limit import reset_checkout_rate_limits
    from worldcup_predictor.billing.webhook_service import get_webhook_service

    reset_auth_rate_limits()
    reset_checkout_rate_limits()

    client = TestClient(app)
    pwd = "Phase39B4-Test-Pass!"

    free_email = f"free39b4-{uuid.uuid4().hex[:8]}@test.local"
    pro_email = f"pro39b4-{uuid.uuid4().hex[:8]}@test.local"
    other_email = f"oth39b4-{uuid.uuid4().hex[:8]}@test.local"

    with saas_uow() as uow:
        free_user = uow.users.create(email=free_email, password_hash=hash_password(pwd), email_verified=True)
        pro_user = uow.users.create(email=pro_email, password_hash=hash_password(pwd), email_verified=True)
        other_user = uow.users.create(email=other_email, password_hash=hash_password(pwd), email_verified=True)
        free_id = free_user.id
        pro_id = pro_user.id
        period_end = datetime(2026, 7, 1, tzinfo=timezone.utc)
        uow.subscriptions.sync_from_stripe(
            pro_id,
            plan=SubscriptionPlan.PRO,
            status=SubscriptionStatus.ACTIVE,
            external_customer_id="cus_pro_test_user",
            billing_status="active",
            current_period_end=period_end,
            last_payment_status="succeeded",
        )
        uow.billing_invoices.upsert_from_stripe(
            user_id=pro_id,
            subscription_id=uow.subscriptions.get_for_user(pro_id).id,
            external_invoice_id=f"in_{uuid.uuid4().hex[:10]}",
            amount_paid=Decimal("19.00"),
            currency="eur",
            status="paid",
            paid_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )

    free_token = issue_access_token_for_record(free_user)
    pro_token = issue_access_token_for_record(pro_user)

    from worldcup_predictor.billing.billing_service import get_billing_service

    app.dependency_overrides[get_billing_service] = lambda: svc

    try:
        r_free = client.get("/api/billing/status", headers={"Authorization": f"Bearer {free_token}"})
        record("free_user_status", r_free.status_code == 200 and r_free.json().get("plan") == "free")
        record("status_no_secrets", _no_secrets(r_free.text))

        r_pro = client.get("/api/billing/status", headers={"Authorization": f"Bearer {pro_token}"})
        pro_body = r_pro.json()
        record(
            "pro_user_status",
            r_pro.status_code == 200
            and pro_body.get("plan") == "pro"
            and pro_body.get("billing_status") == "active",
        )

        r_hist = client.get("/api/billing/history", headers={"Authorization": f"Bearer {pro_token}"})
        hist = r_hist.json()
        record("invoice_history_rows", r_hist.status_code == 200 and len(hist.get("invoices", [])) >= 1)

        r_free_hist = client.get("/api/billing/history", headers={"Authorization": f"Bearer {free_token}"})
        record("free_user_empty_history_ok", r_free_hist.status_code == 200)

        # Users only see own billing (token-scoped)
        record("user_scoped_status", r_pro.json().get("plan") == "pro" and r_free.json().get("plan") == "free")

        r_portal_no_customer = client.post(
            "/api/billing/customer-portal",
            headers={"Authorization": f"Bearer {free_token}"},
            json={},
        )
        record("portal_requires_customer", r_portal_no_customer.status_code == 409)

        r_portal = client.post(
            "/api/billing/customer-portal",
            headers={"Authorization": f"Bearer {pro_token}"},
            json={},
        )
        record(
            "portal_session_created",
            r_portal.status_code == 200 and "portal_url" in r_portal.json(),
        )
        record("portal_response_no_secrets", _no_secrets(r_portal.text))

        r_unauth = client.get("/api/billing/status")
        record("status_requires_auth", r_unauth.status_code == 401)

        # Admin billing summary (super admin route exists — may 403 without gate in test)
        record("admin_billing_route_exists", "admin_user_billing" in (root / "worldcup_predictor/api/routes/admin.py").read_text(encoding="utf-8"))

    finally:
        app.dependency_overrides.pop(get_billing_service, None)

    with saas_uow() as uow:
        uow.users.delete_all_users()

    import subprocess

    for label, script in (
        ("regression_39B3", "validate_phase39b3_stripe_webhooks.py"),
        ("regression_39B2", "validate_phase39b2_stripe_checkout.py"),
        ("regression_39B1", "validate_phase39b1_stripe_foundation.py"),
        ("regression_41B", "validate_phase41b_auth_hardening.py"),
        ("regression_38A", "validate_phase38a_subscription_system.py"),
    ):
        reset_auth_rate_limits()
        reset_checkout_rate_limits()
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
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
