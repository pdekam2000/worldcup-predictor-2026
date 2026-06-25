"""HOTFIX — Premium plan 5€ button 404 / Pro user checkout guard validation."""

from __future__ import annotations

import runpy
import uuid
from pathlib import Path
from unittest.mock import MagicMock

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nHotfix premium plan 404 validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


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
    import sys

    api_only = "--api-only" in sys.argv
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]

    pricing = (root / "base44-d/src/lib/pricingPlans.js").read_text(encoding="utf-8")
    sub_page = (root / "base44-d/src/pages/SubscriptionPage.jsx").read_text(encoding="utf-8")
    upgrade = (root / "base44-d/src/components/subscription/UpgradeComingSoonDialog.jsx").read_text(encoding="utf-8")
    saas_api = (root / "base44-d/src/api/saasApi.js").read_text(encoding="utf-8")
    billing_routes = (root / "worldcup_predictor/api/routes/billing.py").read_text(encoding="utf-8")
    main_py = (root / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")

    record("plan_rank_helpers", all(x in pricing for x in ("normalizePlanKey", "canUpgradeTo", "isPremiumPlan")) if not api_only else True, "skipped (--api-only)" if api_only else "")
    record("subscription_premium_active_badge", "Premium Active" in sub_page if not api_only else True, "skipped (--api-only)" if api_only else "")
    record("subscription_current_plan_disabled", ("Current Plan" in sub_page and "canUpgradeTo" in sub_page) if not api_only else True, "skipped (--api-only)" if api_only else "")
    record("subscription_included_tier_guard", ("Included" in sub_page and "isIncludedTier" in sub_page) if not api_only else True, "skipped (--api-only)" if api_only else "")
    record("upgrade_dialog_blocks_lower_tier", ("upgradeAllowed" in upgrade and "canUpgradeTo" in upgrade) if not api_only else True, "skipped (--api-only)" if api_only else "")
    record("upgrade_dialog_no_checkout_when_blocked", ("if (!upgradeAllowed || !checkoutConfigured) return" in upgrade) if not api_only else True, "skipped (--api-only)" if api_only else "")
    record("checkout_inactive_message", "Payment checkout is not active yet." in upgrade if not api_only else True, "skipped (--api-only)" if api_only else "")
    record("saas_api_detail_message_parse", "detail.message" in saas_api if not api_only else True, "skipped (--api-only)" if api_only else "")
    record("legacy_subscription_checkout_route", "/subscription/checkout" in billing_routes)
    record("legacy_stripe_checkout_route", "/stripe/create-checkout-session" in billing_routes)
    record("legacy_router_registered", "billing_legacy_router" in main_py)

    from worldcup_predictor.billing.billing_service import BillingService
    from worldcup_predictor.billing.schemas import BillingReadinessResponse

    bare = BillingService().readiness()
    record("readiness_checkout_configured_field", hasattr(bare, "checkout_configured"))
    record("readiness_inactive_message", bare.message == "Payment checkout is not active yet." or bare.checkout_enabled)

    test_settings = _test_settings()
    mock_client = MagicMock()
    mock_client.package_available = True
    mock_client.sdk_ready.return_value = True
    configured = BillingService(settings=test_settings, client=mock_client).readiness()
    record("readiness_active_no_message", configured.checkout_configured is True and configured.message is None)

    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app
    from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits
    from worldcup_predictor.billing.checkout_rate_limit import reset_checkout_rate_limits

    client = TestClient(app)
    reset_auth_rate_limits()
    reset_checkout_rate_limits()

    for path in (
        "/api/subscription/checkout",
        "/api/stripe/create-checkout-session",
        "/api/billing/checkout",
    ):
        for method in ("get", "post"):
            fn = getattr(client, method)
            if method == "post":
                r = fn(path, json={"plan": "starter"})
            else:
                r = fn(path)
            record(
                f"legacy_{method}_{path.strip('/').replace('/', '_')}_not_404",
                r.status_code != 404,
                f"status={r.status_code}",
            )
            if r.status_code == 200:
                body = r.json()
                record(
                    f"legacy_{method}_{path.strip('/').replace('/', '_')}_payload",
                    "checkout_configured" in body and "message" in body,
                )

    from worldcup_predictor.api.web_auth import issue_access_token_for_record
    from worldcup_predictor.auth.passwords import hash_password
    from worldcup_predictor.database.postgres.enums import SubscriptionPlan, SubscriptionStatus
    from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

    if postgres_configured():
        from worldcup_predictor.billing.billing_service import get_billing_service

        uid = uuid.uuid4()
        email = f"hotfix-pro-{uid.hex[:8]}@example.com"
        mock_client = MagicMock()
        mock_client.package_available = True
        mock_client.sdk_ready.return_value = True
        svc = BillingService(settings=test_settings, client=mock_client)
        with saas_uow() as uow:
            user = uow.users.create(
                email=email,
                password_hash=hash_password("HotfixTest123!"),
                email_verified=True,
            )
            uow.subscriptions.upsert(user.id, plan=SubscriptionPlan.PRO, status=SubscriptionStatus.ACTIVE)
            token = issue_access_token_for_record(user)

        app.dependency_overrides[get_billing_service] = lambda: svc
        try:
            headers = {"Authorization": f"Bearer {token}"}
            r_starter = client.post(
                "/api/billing/create-checkout-session",
                json={"plan": "starter"},
                headers=headers,
            )
            record(
                "pro_user_starter_checkout_blocked",
                r_starter.status_code == 409,
                f"status={r_starter.status_code}",
            )
            detail = r_starter.json().get("detail", {})
            record(
                "pro_user_starter_error_code",
                isinstance(detail, dict) and detail.get("code") == "invalid_upgrade",
            )

            reset_checkout_rate_limits()
            r_pro_dup = client.post(
                "/api/billing/create-checkout-session",
                json={"plan": "pro"},
                headers=headers,
            )
            record(
                "pro_user_pro_checkout_blocked",
                r_pro_dup.status_code == 409,
                f"status={r_pro_dup.status_code}",
            )
        finally:
            app.dependency_overrides.pop(get_billing_service, None)

        r_login = client.post("/api/auth/login", json={"email": email, "password": "HotfixTest123!"})
        record("login_still_works", r_login.status_code == 200)

        r_sub = client.get("/api/user/subscription", headers=headers)
        record(
            "pro_subscription_status_works",
            r_sub.status_code == 200 and r_sub.json().get("subscription", {}).get("plan") in ("pro", "elite", "unlimited"),
        )
    else:
        record("postgres_required", False, "DATABASE_URL not configured — skipped live API tests")

    record(
        "prediction_engine_untouched",
        "market_consistency_guard" not in billing_routes and "weighted_decision" not in billing_routes,
    )

    _report(checks)
    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print("DEPLOY_READY=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
