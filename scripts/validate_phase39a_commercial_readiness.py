"""Phase 39A — SaaS commercial readiness validation."""

from __future__ import annotations

import json
import runpy
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 39A validation: {passed}/{len(checks)} PASS")
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
    fe = root / "base44-d" / "src"

    pricing = _read = (fe / "components" / "landing" / "PricingSection.jsx").read_text(encoding="utf-8") if (fe / "components" / "landing" / "PricingSection.jsx").exists() else ""
    pricing_page = (fe / "pages" / "PricingPage.jsx").read_text(encoding="utf-8") if (fe / "pages" / "PricingPage.jsx").exists() else ""
    pricing_content = (fe / "components" / "pricing" / "PricingContent.jsx").read_text(encoding="utf-8") if (fe / "components" / "pricing" / "PricingContent.jsx").exists() else ""
    sub = (fe / "pages" / "SubscriptionPage.jsx").read_text(encoding="utf-8") if (fe / "pages" / "SubscriptionPage.jsx").exists() else ""
    upgrade = (fe / "components" / "subscription" / "UpgradeComingSoonDialog.jsx").read_text(encoding="utf-8") if (fe / "components" / "subscription" / "UpgradeComingSoonDialog.jsx").exists() else ""
    app = (fe / "App.jsx").read_text(encoding="utf-8") if (fe / "App.jsx").exists() else ""
    saas = (fe / "api" / "saasApi.js").read_text(encoding="utf-8") if (fe / "api" / "saasApi.js").exists() else ""
    super_admin = (fe / "pages" / "SuperAdminPanel.jsx").read_text(encoding="utf-8") if (fe / "pages" / "SuperAdminPanel.jsx").exists() else ""
    plans_js = (fe / "lib" / "pricingPlans.js").read_text(encoding="utf-8") if (fe / "lib" / "pricingPlans.js").exists() else ""

    record("pricing_page_route", "/pricing" in app and "PricingPage" in app)
    record("pricing_three_plans", "starter" in plans_js and "28" in plans_js and "60" in plans_js)
    record("pricing_comparison_table", "COMPARISON_ROWS" in plans_js and "Compare plans" in pricing_content)
    record("pricing_recommended_starter", "Recommended" in pricing_content and "starter" in pricing_content.lower())
    record("pricing_mobile", "overflow-x-auto" in pricing_content and "md:grid-cols-3" in pricing_content)

    record("subscription_usage_dashboard", "percent" in sub.lower() and "period_start" in sub)
    record("subscription_quota_warnings", "QuotaWarningBanner" in sub and "exhausted" in sub)
    record("subscription_next_reset", "next_reset" in sub.lower() or "period_end" in sub)

    record("upgrade_dialog", "Payment system coming soon" in upgrade)
    record("upgrade_message_admin_shortcut", "Message Admin" in upgrade)
    def _no_payment_processing(text: str) -> bool:
        lower = text.lower()
        triggers = (
            "loadstripe",
            "stripe.checkout",
            "stripe.com",
            "@stripe/stripe-js",
            "create_checkout_session",
            "redirect_to_checkout",
        )
        return not any(t in lower for t in triggers)

    record("upgrade_no_stripe", _no_payment_processing(upgrade))

    record("message_admin_category", "contactCategory" in sub and "CONTACT_CATEGORIES" in sub)
    record("contact_api_category", "category" in saas and "contactAdmin" in saas)

    record("super_admin_analytics", "fetchCommercialAnalytics" in saas and "commercial" in super_admin.lower())
    record("super_admin_plan_counts", "free_users" in super_admin or "starter_users" in super_admin)

    record("email_hidden_frontend", "ADMIN_CONTACT_EMAIL" not in sub and "ADMIN_CONTACT_EMAIL" not in saas)

    from worldcup_predictor.subscription.contact_admin import (
        normalize_contact_category,
        store_contact_message,
        submit_contact_admin,
    )
    from worldcup_predictor.subscription.commercial_analytics import build_commercial_analytics
    from worldcup_predictor.subscription.commercial_readiness import run_commercial_readiness_audit
    from worldcup_predictor.database.postgres.enums import SubscriptionPlan

    record("category_normalize", normalize_contact_category("Subscription") == "subscription")
    record("category_invalid_fallback", normalize_contact_category("hack") == "other")

    with tempfile.TemporaryDirectory() as tmp:
        from worldcup_predictor.config.settings import get_settings
        import os

        os.environ["SUBSCRIPTION_AUDIT_LOG_PATH"] = str(Path(tmp) / "audit.jsonl")
        get_settings.cache_clear()
        settings = get_settings()
        mid = store_contact_message(
            user_id="u1",
            user_email="user@test.com",
            subject="Upgrade",
            message="Want Starter",
            category="subscription",
            settings=settings,
        )
        record("message_stored_with_category", mid > 0)
        submit_contact_admin(
            user_id="u2",
            user_email="u2@test.com",
            subject="Help",
            message="Support please",
            category="support",
            ip="127.0.0.1",
            settings=settings,
        )
        audit = Path(tmp).joinpath("audit.jsonl").read_text(encoding="utf-8")
        record("audit_category_logged", "category=support" in audit or "contact_admin" in audit)

    analytics = build_commercial_analytics()
    record("analytics_structure", "total_users" in analytics and "contact_messages_count" in analytics)

    readiness = run_commercial_readiness_audit()
    record("readiness_score_generated", readiness.get("readiness_score", 0) >= 70, f"score={readiness.get('readiness_score')}")

    from worldcup_predictor.subscription.quota_service import get_user_quota_status
    from worldcup_predictor.subscription.plan_limits import PLAN_MONTHLY_PREDICTION_LIMITS

    uid = str(uuid.uuid4())
    with patch("worldcup_predictor.subscription.quota_service._resolve_subscription") as mock_sub:
        from datetime import datetime, timezone
        mock_sub.return_value = (SubscriptionPlan.FREE, datetime(2026, 1, 1, tzinfo=timezone.utc))
        q = get_user_quota_status(uid, role="user")
        record("free_quota_4", q.monthly_limit == PLAN_MONTHLY_PREDICTION_LIMITS["free"])

    try:
        from fastapi.testclient import TestClient
        from worldcup_predictor.api.main import app

        client = TestClient(app)
        r = client.get("/api/admin/commercial/analytics")
        record("commercial_analytics_unauth", r.status_code == 401)
        r2 = client.post("/api/user/contact-admin", json={"subject": "x", "message": "y", "category": "billing"})
        record("contact_unauth_401", r2.status_code == 401)
    except Exception as exc:
        record("api_smoke", False, str(exc))

    # Quota warning fields in API
    from worldcup_predictor.api.routes.user import get_user_quota
    record("quota_percent_in_route", "percent_used" in open(root / "worldcup_predictor/api/routes/user.py", encoding="utf-8").read())

    record("no_payment_processing", _no_payment_processing(sub) and _no_payment_processing(saas))

    _report(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
