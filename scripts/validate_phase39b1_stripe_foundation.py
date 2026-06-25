"""Phase 39B-1 — Stripe foundation validation (DB + config + client skeleton)."""

from __future__ import annotations

import json
import os
import runpy
import tempfile
from pathlib import Path
from unittest.mock import patch

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 39B-1 validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def _no_secrets(text: str) -> bool:
    lower = text.lower()
    banned = ("sk_test_", "sk_live_", "whsec_", "price_1")
    return not any(b in lower for b in banned)


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]
    mig = root / "alembic" / "versions" / "004_stripe_billing_foundation.py"
    record("migration_file_exists", mig.exists())

    mig_text = mig.read_text(encoding="utf-8") if mig.exists() else ""
    record("migration_billing_invoices", "billing_invoices" in mig_text)
    record("migration_stripe_webhook_events", "stripe_webhook_events" in mig_text)
    record("migration_subscriptions_extended", "external_customer_id" in mig_text and "billing_status" in mig_text)
    record("migration_reversible", "def downgrade" in mig_text)

    from worldcup_predictor.database.postgres.models import BillingInvoice, StripeWebhookEvent, Subscription
    sub_cols = {c.name for c in Subscription.__table__.columns}
    record("orm_external_customer_id", "external_customer_id" in sub_cols)
    record("orm_billing_invoices_table", BillingInvoice.__tablename__ == "billing_invoices")
    record("orm_stripe_webhook_events_table", StripeWebhookEvent.__tablename__ == "stripe_webhook_events")

    from worldcup_predictor.config.settings import Settings, get_settings

    get_settings.cache_clear()
    with patch.dict(os.environ, {}, clear=False):
        for key in (
            "STRIPE_SECRET_KEY",
            "STRIPE_WEBHOOK_SECRET",
            "STRIPE_STARTER_PRICE_ID",
            "STRIPE_PRO_PRICE_ID",
            "STRIPE_SUCCESS_URL",
            "STRIPE_CANCEL_URL",
            "STRIPE_MODE",
        ):
            os.environ.pop(key, None)
        get_settings.cache_clear()
        bare = Settings()
        record("app_starts_without_stripe_env", bare.stripe_mode_normalized == "missing")

    from worldcup_predictor.config.provider_readiness import provider_diagnostic, stripe_env_diagnostic

    get_settings.cache_clear()
    diag = provider_diagnostic(get_settings())
    stripe_diag = stripe_env_diagnostic(get_settings())
    record("diagnostic_stripe_keys", "STRIPE_SECRET_KEY_present" in diag)
    record("diagnostic_stripe_mode", diag.get("STRIPE_MODE") in ("missing", "test", "live"))
    dumped = json.dumps({**diag, **stripe_diag})
    record("diagnostic_no_secrets", _no_secrets(dumped))

    from worldcup_predictor.billing.billing_service import BillingService
    from worldcup_predictor.billing.schemas import PlanPriceMappingError

    svc = BillingService()
    ready = svc.readiness()
    record("readiness_checkout_disabled", ready.checkout_enabled is False)
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

    test_settings = Settings.model_construct(
        stripe_secret_key="sk_test_placeholder",
        stripe_starter_price_id="price_starter_test",
        stripe_pro_price_id="price_pro_test",
        stripe_success_url="https://example.com/success",
        stripe_cancel_url="https://example.com/cancel",
        stripe_mode="test",
    )
    svc2 = BillingService(settings=test_settings)
    record("starter_price_mapping", svc2.plan_to_price_id("starter") == "price_starter_test")
    record("pro_price_mapping", svc2.plan_to_price_id("pro") == "price_pro_test")
    ready2 = svc2.readiness()
    pkg_ok = ready2.stripe_package_available
    record(
        "readiness_configured_with_env",
        ready2.stripe_mode == "test"
        and ready2.starter_price_configured
        and ready2.pro_price_configured
        and ready2.checkout_enabled is pkg_ok,
        f"checkout_enabled={ready2.checkout_enabled}",
    )

    from worldcup_predictor.billing.stripe_client import StripeClient

    with patch("worldcup_predictor.billing.stripe_client._STRIPE_AVAILABLE", False):
        client = StripeClient(test_settings)
        record("missing_stripe_package_graceful", client.package_available is False and client.sdk_ready() is False)

    try:
        from fastapi.testclient import TestClient
        from worldcup_predictor.api.main import app

        client = TestClient(app)
        r = client.get("/api/billing/readiness")
        record("readiness_unauth_401", r.status_code == 401)
        r2 = client.get("/api/health")
        record("app_starts_health_ok", r2.status_code == 200)
    except Exception as exc:
        record("api_smoke", False, str(exc))

    fe = root / "base44-d" / "src" / "api" / "saasApi.js"
    if fe.exists():
        saas = fe.read_text(encoding="utf-8")
        record("frontend_fetchBillingReadiness", "fetchBillingReadiness" in saas)
        upgrade = (root / "base44-d" / "src" / "components" / "subscription" / "UpgradeComingSoonDialog.jsx")
        if upgrade.exists():
            record("upgrade_still_coming_soon", "Payment system coming soon" in upgrade.read_text(encoding="utf-8"))

    # Optional: run alembic if DATABASE_URL configured
    import sys

    db_url = os.environ.get("DATABASE_URL", "") or get_settings().database_url
    if db_url.strip():
        try:
            import subprocess

            proc = subprocess.run(
                [sys.executable, "-m", "alembic", "current"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            record("alembic_reachable", proc.returncode == 0, (proc.stdout or proc.stderr)[:80])
        except Exception as exc:
            record("alembic_reachable", False, str(exc)[:80])
    else:
        record("alembic_reachable", True, "skipped_no_database_url")

    _report(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
