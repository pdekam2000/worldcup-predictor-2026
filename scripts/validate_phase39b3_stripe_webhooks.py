"""Phase 39B-3 — Stripe webhook processing validation."""

from __future__ import annotations

import json
import runpy
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 39B-3 validation: {passed}/{len(checks)} PASS")
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
        stripe_webhook_secret="whsec_test_phase39b3_secret",
        stripe_starter_price_id="price_starter_test",
        stripe_pro_price_id="price_pro_test",
        stripe_success_url="https://example.com/billing/success",
        stripe_cancel_url="https://example.com/billing/cancel",
        stripe_mode="test",
    )


def _stripe_event(event_id: str, event_type: str, obj: dict) -> dict:
    return {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "api_version": "2023-10-16",
        "livemode": False,
        "data": {"object": obj},
    }


def _subscription_obj(
    *,
    sub_id: str,
    customer_id: str,
    user_id: str,
    price_id: str,
    status: str = "active",
    period_start: int | None = None,
    period_end: int | None = None,
    cancel_at_period_end: bool = False,
) -> dict:
    now = int(time.time())
    return {
        "id": sub_id,
        "object": "subscription",
        "customer": customer_id,
        "status": status,
        "metadata": {"user_id": user_id},
        "current_period_start": period_start or now,
        "current_period_end": period_end or (now + 30 * 86400),
        "cancel_at_period_end": cancel_at_period_end,
        "items": {
            "data": [{"price": {"id": price_id}}],
        },
    }


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    from stripe._webhook import WebhookSignature

    timestamp = int(time.time())
    payload = payload_bytes.decode("utf-8")
    signed_payload = f"{timestamp}.{payload}"
    signature = WebhookSignature._compute_signature(signed_payload, secret)
    return f"t={timestamp},v1={signature}"


def _post_webhook(client, event: dict, secret: str, *, auth: str | None = None):
    payload = json.dumps(event).encode("utf-8")
    headers = {"Stripe-Signature": _sign_payload(payload, secret)}
    if auth:
        headers["Authorization"] = auth
    return client.post("/api/billing/webhook", content=payload, headers=headers)


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]
    record("webhook_service_exists", (root / "worldcup_predictor/billing/webhook_service.py").is_file())
    record("webhook_handlers_exists", (root / "worldcup_predictor/billing/webhook_handlers.py").is_file())
    record("webhook_route", '"/webhook"' in (root / "worldcup_predictor/api/routes/billing.py").read_text(encoding="utf-8"))

    from worldcup_predictor.billing.plan_mapping import price_id_to_plan
    from worldcup_predictor.billing.webhook_service import WebhookService
    from worldcup_predictor.config.settings import Settings
    from worldcup_predictor.database.postgres.enums import SubscriptionPlan, SubscriptionStatus
    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

    test_settings = _test_settings()
    record("starter_price_maps", price_id_to_plan("price_starter_test", test_settings) == SubscriptionPlan.STARTER)
    record("pro_price_maps", price_id_to_plan("price_pro_test", test_settings) == SubscriptionPlan.PRO)
    record("unknown_price_none", price_id_to_plan("price_unknown_xyz", test_settings) is None)

    if not postgres_configured():
        record("postgres_required", False, "DATABASE_URL not configured")
        _report(checks)
        return 1

    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app
    from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits
    from worldcup_predictor.auth.passwords import hash_password
    from worldcup_predictor.billing.checkout_rate_limit import reset_checkout_rate_limits
    from worldcup_predictor.billing.webhook_service import get_webhook_service
    from worldcup_predictor.subscription.quota_service import get_user_quota_status

    reset_auth_rate_limits()
    reset_checkout_rate_limits()

    client = TestClient(app)
    pwd = "Phase39B3-Test-Pass!"
    secret = test_settings.stripe_webhook_secret
    starter_price = test_settings.stripe_starter_price_id
    pro_price = test_settings.stripe_pro_price_id

    svc = WebhookService(settings=test_settings)
    app.dependency_overrides[get_webhook_service] = lambda: svc

    try:
        # Invalid signature
        bad_event = _stripe_event("evt_bad_sig", "customer.subscription.created", {})
        bad_payload = json.dumps(bad_event).encode()
        r_bad = client.post(
            "/api/billing/webhook",
            content=bad_payload,
            headers={"Stripe-Signature": "t=0,v1=invalidsignature"},
        )
        record("invalid_signature_rejected", r_bad.status_code == 400)
        record("invalid_sig_no_secrets", _no_secrets(r_bad.text))

        # Create test user
        email = f"wh39b3-{uuid.uuid4().hex[:8]}@test.local"
        user_id: str
        with saas_uow() as uow:
            user = uow.users.create(email=email, password_hash=hash_password(pwd), email_verified=True)
            user_id = str(user.id)
            uow.subscriptions.get_or_create_free(user.id)

        customer_id = f"cus_{uuid.uuid4().hex[:12]}"
        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        period_start = int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp())
        period_end = int(datetime(2026, 7, 1, tzinfo=timezone.utc).timestamp())

        # No JWT required
        checkout_evt = _stripe_event(
            f"evt_checkout_{uuid.uuid4().hex[:8]}",
            "checkout.session.completed",
            {
                "id": "cs_mock_checkout",
                "object": "checkout.session",
                "mode": "subscription",
                "payment_status": "paid",
                "customer": customer_id,
                "subscription": sub_id,
                "metadata": {"user_id": user_id, "requested_plan": "starter"},
            },
        )
        r_checkout = _post_webhook(client, checkout_evt, secret)
        record("checkout_completed_stored", r_checkout.status_code == 200)
        record("no_jwt_required", r_checkout.status_code == 200)

        with saas_uow() as uow:
            sub = uow.subscriptions.get_for_user(uuid.UUID(user_id))
            checkout_linked = (
                uow.subscriptions.get_external_customer_id(uuid.UUID(user_id)) == customer_id
                and sub is not None
                and sub.plan == SubscriptionPlan.FREE
            )
        record("checkout_no_plan_activation", checkout_linked)

        # subscription.created activates starter
        created_evt = _stripe_event(
            f"evt_sub_created_{uuid.uuid4().hex[:8]}",
            "customer.subscription.created",
            _subscription_obj(
                sub_id=sub_id,
                customer_id=customer_id,
                user_id=user_id,
                price_id=starter_price,
                status="active",
                period_start=period_start,
                period_end=period_end,
            ),
        )
        r_created = _post_webhook(client, created_evt, secret)
        record("subscription_created_200", r_created.status_code == 200)

        with saas_uow() as uow:
            sub = uow.subscriptions.get_for_user(uuid.UUID(user_id))
            starter_active = (
                sub is not None
                and sub.plan == SubscriptionPlan.STARTER
                and sub.status == SubscriptionStatus.ACTIVE
                and sub.start_date is not None
            )
        record("starter_activated", starter_active)

        quota = get_user_quota_status(user_id)
        anchor_ok = False
        if starter_active and sub.start_date is not None:
            anchor_ok = sub.start_date.day == 1 and sub.start_date.month == 6
        record("billing_anchor_synced", anchor_ok)

        # subscription.updated upgrade to pro
        updated_evt = _stripe_event(
            f"evt_sub_up_{uuid.uuid4().hex[:8]}",
            "customer.subscription.updated",
            _subscription_obj(
                sub_id=sub_id,
                customer_id=customer_id,
                user_id=user_id,
                price_id=pro_price,
                status="active",
                period_start=period_start,
                period_end=period_end,
            ),
        )
        r_updated = _post_webhook(client, updated_evt, secret)
        with saas_uow() as uow:
            sub = uow.subscriptions.get_for_user(uuid.UUID(user_id))
            pro_active = sub is not None and sub.plan == SubscriptionPlan.PRO
        record("subscription_updated_pro", r_updated.status_code == 200 and pro_active)

        # invoice.payment_succeeded (before unknown-price test mutates Stripe IDs)
        inv_id = f"in_{uuid.uuid4().hex[:12]}"
        inv_evt = _stripe_event(
            f"evt_inv_ok_{uuid.uuid4().hex[:8]}",
            "invoice.payment_succeeded",
            {
                "id": inv_id,
                "object": "invoice",
                "customer": customer_id,
                "subscription": sub_id,
                "amount_due": 1900,
                "amount_paid": 1900,
                "currency": "eur",
                "status": "paid",
                "period_start": period_start,
                "period_end": period_end,
                "hosted_invoice_url": "https://invoice.stripe.test/hosted",
                "status_transitions": {"paid_at": period_start},
            },
        )
        r_inv = _post_webhook(client, inv_evt, secret)
        with saas_uow() as uow:
            from sqlalchemy import select

            from worldcup_predictor.database.postgres.models import BillingInvoice

            row = uow.session.scalar(
                select(BillingInvoice).where(BillingInvoice.external_invoice_id == inv_id)
            )
            invoice_created = row is not None
        record("invoice_payment_succeeded", r_inv.status_code == 200 and invoice_created)

        # unknown price does not activate paid plan (separate user — avoids overwriting Stripe IDs)
        unknown_email = f"unk39b3-{uuid.uuid4().hex[:8]}@test.local"
        with saas_uow() as uow:
            unk_user = uow.users.create(
                email=unknown_email, password_hash=hash_password(pwd), email_verified=True
            )
            unk_uid = str(unk_user.id)
            uow.subscriptions.get_or_create_free(unk_user.id)
        unknown_evt = _stripe_event(
            f"evt_unknown_{uuid.uuid4().hex[:8]}",
            "customer.subscription.updated",
            _subscription_obj(
                sub_id=f"sub_unknown_{uuid.uuid4().hex[:8]}",
                customer_id=f"cus_unknown_{uuid.uuid4().hex[:8]}",
                user_id=unk_uid,
                price_id="price_unknown_xyz",
                status="active",
            ),
        )
        r_unknown = _post_webhook(client, unknown_evt, secret)
        with saas_uow() as uow:
            unk_sub = uow.subscriptions.get_for_user(uuid.UUID(unk_uid))
            unknown_free = unk_sub is not None and unk_sub.plan == SubscriptionPlan.FREE
        record("unknown_price_no_activation", r_unknown.status_code == 200 and unknown_free)

        # invoice.payment_failed — new free user should not get paid plan
        free_email = f"fail39b3-{uuid.uuid4().hex[:8]}@test.local"
        with saas_uow() as uow:
            free_user = uow.users.create(
                email=free_email, password_hash=hash_password(pwd), email_verified=True
            )
            free_uid = str(free_user.id)
            uow.subscriptions.get_or_create_free(free_user.id)
            fail_customer = f"cus_fail_{uuid.uuid4().hex[:8]}"
            uow.subscriptions.set_external_customer_id(free_user.id, fail_customer)

        fail_inv = _stripe_event(
            f"evt_inv_fail_{uuid.uuid4().hex[:8]}",
            "invoice.payment_failed",
            {
                "id": f"in_fail_{uuid.uuid4().hex[:8]}",
                "object": "invoice",
                "customer": fail_customer,
                "subscription": f"sub_fail_{uuid.uuid4().hex[:8]}",
                "amount_due": 500,
                "amount_paid": 0,
                "currency": "eur",
                "status": "open",
                "period_start": period_start,
                "period_end": period_end,
            },
        )
        r_fail = _post_webhook(client, fail_inv, secret)
        with saas_uow() as uow:
            free_sub = uow.subscriptions.get_for_user(uuid.UUID(free_uid))
            no_activation = free_sub is not None and free_sub.plan == SubscriptionPlan.FREE
        record("invoice_failed_no_activation", r_fail.status_code == 200 and no_activation)

        # duplicate event ignored
        r_dup = _post_webhook(client, created_evt, secret)
        record("duplicate_event_ignored", r_dup.status_code == 200 and r_dup.json().get("status") == "duplicate")

        # subscription.deleted downgrades to free
        deleted_evt = _stripe_event(
            f"evt_sub_del_{uuid.uuid4().hex[:8]}",
            "customer.subscription.deleted",
            _subscription_obj(
                sub_id=sub_id,
                customer_id=customer_id,
                user_id=user_id,
                price_id=pro_price,
                status="canceled",
                period_start=period_start,
                period_end=period_end,
            ),
        )
        r_deleted = _post_webhook(client, deleted_evt, secret)
        with saas_uow() as uow:
            sub = uow.subscriptions.get_for_user(uuid.UUID(user_id))
            downgraded = sub is not None and sub.plan == SubscriptionPlan.FREE
            customer_kept = uow.subscriptions.get_external_customer_id(uuid.UUID(user_id)) == customer_id
        record("subscription_deleted_free", r_deleted.status_code == 200 and downgraded and customer_kept)

        # missing user metadata does not crash
        missing_evt = _stripe_event(
            f"evt_missing_{uuid.uuid4().hex[:8]}",
            "checkout.session.completed",
            {
                "id": "cs_missing_meta",
                "object": "checkout.session",
                "mode": "subscription",
                "payment_status": "paid",
                "customer": "cus_missing",
                "metadata": {},
            },
        )
        r_missing = _post_webhook(client, missing_evt, secret)
        record("missing_metadata_no_crash", r_missing.status_code == 200)

        record("webhook_response_no_secrets", _no_secrets(r_created.text + r_inv.text))

    finally:
        app.dependency_overrides.clear()

    with saas_uow() as uow:
        uow.users.delete_all_users()

    import subprocess

    for label, script in (
        ("regression_39B2", "validate_phase39b2_stripe_checkout.py"),
        ("regression_39B1", "validate_phase39b1_stripe_foundation.py"),
        ("regression_41B", "validate_phase41b_auth_hardening.py"),
        ("regression_41A", "validate_phase41a_smtp_email_operations.py"),
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
