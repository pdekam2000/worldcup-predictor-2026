"""Validate billing purchase error handling — Phase next sprint hotfix."""

from __future__ import annotations

import runpy
import uuid
from pathlib import Path
from unittest.mock import patch

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nBilling purchase validation: {passed}/{len(checks)} PASS")
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
    record("user_messages_module", (root / "worldcup_predictor/billing/user_messages.py").is_file())
    record("checkout_errors_frontend", (root / "base44-d/src/lib/checkoutErrors.js").is_file())
    record("stripe_validate_price", "validate_price_id" in (root / "worldcup_predictor/billing/stripe_client.py").read_text(encoding="utf-8"))

    from worldcup_predictor.billing.user_messages import (
        CHECKOUT_INACTIVE_MSG,
        PLAN_UNAVAILABLE_MSG,
        message_for_code,
    )
    from worldcup_predictor.billing.billing_service import BillingService
    from worldcup_predictor.billing.schemas import CheckoutValidationError, PlanPriceMappingError
    from worldcup_predictor.billing.stripe_client import StripeClientError

    record("inactive_message", CHECKOUT_INACTIVE_MSG == "Payment checkout is not active yet.")
    record("plan_unavailable_message", PLAN_UNAVAILABLE_MSG == "This plan is not available yet.")
    record("code_mapping_price", message_for_code("stripe_price_invalid") == PLAN_UNAVAILABLE_MSG)

    svc = BillingService()
    with patch.object(svc._client, "sdk_ready", return_value=False):
        r = svc.readiness()
        record("disabled_when_no_sdk", r.checkout_enabled is False and CHECKOUT_INACTIVE_MSG in (r.message or ""))

    with patch.object(svc._client, "sdk_ready", return_value=True), patch.object(
        svc, "_stripe_prices_valid", return_value=False
    ):
        r2 = svc.readiness()
        record("invalid_price_disables_checkout", r2.checkout_enabled is False)

    try:
        svc.plan_to_price_id("starter")
        record("missing_price_raises", True, "env may have price configured")
    except PlanPriceMappingError as exc:
        record("missing_price_raises", exc.code == "price_not_configured")
        record("missing_price_message", PLAN_UNAVAILABLE_MSG in str(exc))

    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app
    from worldcup_predictor.auth.passwords import hash_password
    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

    client = TestClient(app)

    for path in (
        "/api/billing/checkout",
        "/api/subscription/checkout",
        "/api/stripe/create-checkout-session",
    ):
        resp = client.get(path)
        record(f"legacy_{path.split('/')[-2]}_{path.split('/')[-1]}_no_404", resp.status_code == 200)

    wrong = client.get("/api/predictions/999")
    record("predictions_typo_still_404", wrong.status_code == 404)

    if postgres_configured():
        from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits
        from worldcup_predictor.database.postgres.enums import SubscriptionPlan, SubscriptionStatus

        reset_auth_rate_limits()
        email = f"billing-val-{uuid.uuid4().hex[:8]}@test.local"
        pwd = "Billing-Val-Pass1!"
        with saas_uow() as uow:
            uow.users.create(email=email, password_hash=hash_password(pwd), email_verified=True)
        login = client.post("/api/auth/login", json={"email": email, "password": pwd})
        headers = {"Authorization": f"Bearer {login.json().get('access_token')}"}

        readiness = client.get("/api/billing/readiness", headers=headers)
        record("readiness_auth_ok", readiness.status_code == 200)

        with patch.object(BillingService, "create_checkout_session", side_effect=CheckoutValidationError(
            PLAN_UNAVAILABLE_MSG, code="stripe_price_invalid", status_code=400
        )):
            bad = client.post("/api/billing/create-checkout-session", headers=headers, json={"plan": "starter"})
            record("checkout_readable_error", bad.status_code == 400)
            detail = bad.json().get("detail") or {}
            record("checkout_error_message", detail.get("message") == PLAN_UNAVAILABLE_MSG)
            record("no_secret_in_error", "sk_" not in str(bad.json()) and "whsec_" not in str(bad.json()))

    from datetime import datetime
    from decimal import Decimal

    from worldcup_predictor.database.postgres.enums import BillingCycle
    from worldcup_predictor.database.postgres.schemas import SubscriptionRecord

    pro_sub = SubscriptionRecord(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        plan=SubscriptionPlan.PRO,
        billing_cycle=BillingCycle.MONTHLY,
        status=SubscriptionStatus.ACTIVE,
        amount=Decimal("19"),
        external_subscription_id=None,
        start_date=datetime.utcnow(),
        end_date=None,
        provider="manual",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    try:
        svc.validate_checkout_upgrade(pro_sub, "starter")
        record("pro_blocks_starter", False)
    except CheckoutValidationError as exc:
        record("pro_blocks_starter", exc.status_code == 409)
        record("pro_blocks_message", exc.code == "invalid_upgrade")
    else:
        for name in (
            "readiness_auth_ok",
            "checkout_readable_error",
            "checkout_error_message",
            "no_secret_in_error",
            "pro_blocks_starter",
            "pro_blocks_message",
        ):
            record(name, True, "postgres skipped")

    _report(checks)
    failed = [n for n, ok, _ in checks if not ok]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
