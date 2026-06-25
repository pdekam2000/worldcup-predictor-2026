"""Phase 39B-2 — Stripe checkout session validation."""

from __future__ import annotations

import json
import os
import runpy
import sys
import uuid
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 39B-2 validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def _no_secrets(text: str) -> bool:
    lower = text.lower()
    banned = ("sk_test_", "sk_live_", "whsec_", "price_1", "cs_test_", "cs_live_")
    return not any(b in lower for b in banned)


def _test_settings():
    from worldcup_predictor.config.settings import Settings, get_settings

    base = get_settings()
    return Settings.model_construct(
        database_url=base.database_url,
        app_env=base.app_env,
        stripe_secret_key="sk_test_placeholder",
        stripe_starter_price_id="price_starter_test",
        stripe_pro_price_id="price_pro_test",
        stripe_success_url="https://example.com/billing/success",
        stripe_cancel_url="https://example.com/billing/cancel",
        stripe_mode="test",
    )


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]

    record("billing_service_exists", (root / "worldcup_predictor/billing/billing_service.py").is_file())
    record("checkout_endpoint_route", "create-checkout-session" in (root / "worldcup_predictor/api/routes/billing.py").read_text(encoding="utf-8"))
    record("frontend_createCheckoutSession", "createCheckoutSession" in (root / "base44-d/src/api/saasApi.js").read_text(encoding="utf-8"))
    record("billing_success_page", (root / "base44-d/src/pages/BillingCheckoutSuccess.jsx").is_file())
    record("billing_cancel_page", (root / "base44-d/src/pages/BillingCheckoutCancel.jsx").is_file())

    upgrade = (root / "base44-d/src/components/subscription/UpgradeComingSoonDialog.jsx").read_text(encoding="utf-8")
    record("upgrade_coming_soon_fallback", "Payment system coming soon" in upgrade)
    record("upgrade_checkout_when_enabled", "createCheckoutSession" in upgrade and "checkout_enabled" in upgrade)

    from worldcup_predictor.billing.billing_service import BillingService, get_billing_service
    from worldcup_predictor.billing.checkout_rate_limit import reset_checkout_rate_limits
    from worldcup_predictor.billing.schemas import PlanPriceMappingError
    from worldcup_predictor.config.settings import Settings, get_settings
    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

    bare = Settings()
    bare_ready = BillingService(settings=bare).readiness()
    record("missing_env_checkout_disabled", bare_ready.checkout_enabled is False)

    test_settings = _test_settings()
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.package_available = True
    mock_client.sdk_ready.return_value = True
    mock_client.create_customer.return_value = "cus_test_123"
    mock_client.create_checkout_session.return_value = (
        "https://checkout.stripe.test/session/test",
        "sess_mock_checkout_123",
    )

    svc = BillingService(settings=test_settings, client=mock_client)
    ready = svc.readiness()
    record("readiness_checkout_enabled", ready.checkout_enabled is True)
    record("readiness_no_secrets", _no_secrets(json.dumps(ready.model_dump())))

    try:
        svc.plan_to_price_id("free")
        record("free_checkout_rejected", False)
    except PlanPriceMappingError as exc:
        record("free_checkout_rejected", exc.code == "free_plan")

    try:
        svc.plan_to_price_id("enterprise")
        record("unknown_plan_rejected", False)
    except PlanPriceMappingError as exc:
        record("unknown_plan_rejected", exc.code == "unknown_plan")

    if not postgres_configured():
        record("postgres_required", False, "DATABASE_URL not configured")
        _report(checks)
        return 1

    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app
    from worldcup_predictor.api.web_auth import issue_access_token_for_record
    from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits
    from worldcup_predictor.auth.passwords import hash_password
    from worldcup_predictor.database.postgres.enums import SubscriptionPlan, SubscriptionStatus

    reset_auth_rate_limits()
    reset_checkout_rate_limits()

    client = TestClient(app)
    pwd = "Phase39B2-Test-Pass!"

    r_unauth = client.post("/api/billing/create-checkout-session", json={"plan": "starter"})
    record("unauthenticated_blocked", r_unauth.status_code == 401)

    unv_email = f"unv39b2-{uuid.uuid4().hex[:8]}@test.local"
    with saas_uow() as uow:
        unv = uow.users.create(email=unv_email, password_hash=hash_password(pwd), email_verified=False)
        unv_token = issue_access_token_for_record(unv)
    r_unv = client.post(
        "/api/billing/create-checkout-session",
        json={"plan": "starter"},
        headers={"Authorization": f"Bearer {unv_token}"},
    )
    record("unverified_blocked", r_unv.status_code == 403)

    ban_email = f"ban39b2-{uuid.uuid4().hex[:8]}@test.local"
    with saas_uow() as uow:
        banned = uow.users.create(email=ban_email, password_hash=hash_password(pwd), email_verified=True)
        uow.users.set_banned(banned.id, reason="test")
        ban_token = issue_access_token_for_record(uow.users.get_by_id(banned.id))

    r_ban = client.post(
        "/api/billing/create-checkout-session",
        json={"plan": "starter"},
        headers={"Authorization": f"Bearer {ban_token}"},
    )
    record("banned_blocked", r_ban.status_code in (401, 403))

    free_email = f"free39b2-{uuid.uuid4().hex[:8]}@test.local"
    with saas_uow() as uow:
        free_user = uow.users.create(email=free_email, password_hash=hash_password(pwd), email_verified=True)
        free_id = free_user.id
        free_token = issue_access_token_for_record(free_user)

    app.dependency_overrides[get_billing_service] = lambda: svc

    try:
        r_free = client.post(
            "/api/billing/create-checkout-session",
            json={"plan": "free"},
            headers={"Authorization": f"Bearer {free_token}"},
        )
        record("free_plan_rejected", r_free.status_code == 400)

        r_unknown = client.post(
            "/api/billing/create-checkout-session",
            json={"plan": "enterprise"},
            headers={"Authorization": f"Bearer {free_token}"},
        )
        record("unknown_plan_rejected_api", r_unknown.status_code == 400)

        r_starter = client.post(
            "/api/billing/create-checkout-session",
            json={"plan": "starter"},
            headers={"Authorization": f"Bearer {free_token}"},
        )
        record("starter_checkout_created", r_starter.status_code == 200 and "checkout_url" in r_starter.json())
        record("starter_response_no_secrets", _no_secrets(r_starter.text))

        with saas_uow() as uow:
            sub_after = uow.subscriptions.get_for_user(free_id)
            plan_unchanged = sub_after.plan == SubscriptionPlan.FREE
            customer_set = uow.subscriptions.get_external_customer_id(free_id) == "cus_test_123"
        record("no_plan_activation_after_checkout", plan_unchanged)
        record("stripe_customer_stored", customer_set)

        mock_client.create_customer.reset_mock()
        reset_checkout_rate_limits()
        r_pro = client.post(
            "/api/billing/create-checkout-session",
            json={"plan": "pro"},
            headers={"Authorization": f"Bearer {free_token}"},
        )
        record("pro_checkout_created", r_pro.status_code == 200)
        record("customer_reused", mock_client.create_customer.call_count == 0)

        with saas_uow() as uow:
            uow.subscriptions.upsert(free_id, plan=SubscriptionPlan.PRO, status=SubscriptionStatus.ACTIVE)
        reset_checkout_rate_limits()
        r_dup = client.post(
            "/api/billing/create-checkout-session",
            json={"plan": "pro"},
            headers={"Authorization": f"Bearer {free_token}"},
        )
        record("duplicate_active_pro_blocked", r_dup.status_code == 409, f"status={r_dup.status_code}")

    finally:
        app.dependency_overrides.pop(get_billing_service, None)

    # Readiness unauth
    r_ready = client.get("/api/billing/readiness")
    record("readiness_unauth_401", r_ready.status_code == 401)

    with saas_uow() as uow:
        uow.users.delete_all_users()

    import subprocess

    for label, script in (
        ("regression_39B1", "validate_phase39b1_stripe_foundation.py"),
        ("regression_41B", "validate_phase41b_auth_hardening.py"),
        ("regression_41A", "validate_phase41a_smtp_email_operations.py"),
        ("regression_40A", "validate_phase40a_auth_user_management.py"),
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
