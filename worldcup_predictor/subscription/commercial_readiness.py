"""Phase 39A — SaaS commercial readiness audit and score."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    p = ROOT / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


def run_commercial_readiness_audit() -> dict:
    checks: list[dict] = []

    def add(name: str, ok: bool, weight: int, detail: str = "") -> None:
        checks.append({"name": name, "pass": ok, "weight": weight, "detail": detail, "score": weight if ok else 0})

    app = _read("base44-d/src/App.jsx")
    pricing_section = _read("base44-d/src/components/landing/PricingSection.jsx")
    pricing_content = _read("base44-d/src/components/pricing/PricingContent.jsx")
    pricing_plans = _read("base44-d/src/lib/pricingPlans.js")
    pricing_page = _read("base44-d/src/pages/PricingPage.jsx")
    sub = _read("base44-d/src/pages/SubscriptionPage.jsx")
    upgrade = _read("base44-d/src/components/subscription/UpgradeComingSoonDialog.jsx")
    saas = _read("base44-d/src/api/saasApi.js")
    super_admin = _read("base44-d/src/pages/SuperAdminPanel.jsx")
    contact = _read("worldcup_predictor/subscription/contact_admin.py")

    add("user_onboarding", "/register" in app and "/login" in app, 10)
    add(
        "pricing_page",
        "Starter" in pricing_plans and "PricingContent" in pricing_section,
        10,
        "landing + dedicated pricing page",
    )
    add("pricing_route", "/pricing" in app or bool(pricing_page), 5, "public pricing route")
    add(
        "subscription_dashboard",
        "used_this_period" in sub and ("period_start" in sub or "percent" in sub.lower()),
        12,
    )
    add("quota_tracking", "monthly_limit" in sub or "remaining" in sub, 12)
    add(
        "upgrade_path",
        "Payment system coming soon" in upgrade or "Payment system coming soon" in sub,
        10,
    )
    add(
        "message_admin",
        "contactAdmin" in saas and ("category" in sub.lower() or "Category" in sub),
        10,
    )
    add("admin_tools", "fetchAdminUserUsage" in saas or "resetAdminUserQuota" in saas, 8)
    add(
        "super_admin_analytics",
        "fetchCommercialAnalytics" in saas or "commercial" in super_admin.lower(),
        8,
        "commercial analytics panel",
    )
    add("mobile_responsive", "sm:" in pricing_content and "sm:" in sub, 8)
    add("security_no_email_exposed", "ADMIN_CONTACT_EMAIL" not in sub and "ADMIN_CONTACT_EMAIL" not in saas, 7)
    add("audit_logging", "write_subscription_audit" in contact, 5)
    payment_triggers = ("loadstripe", "stripe.checkout", "@stripe/stripe-js", "create_checkout_session")
    add(
        "no_stripe_yet",
        not any(t in sub.lower() for t in payment_triggers)
        and not any(t in upgrade.lower() for t in payment_triggers),
        5,
    )

    max_score = sum(c["weight"] for c in checks)
    score = sum(c["score"] for c in checks)
    pct = round((score / max_score) * 100) if max_score else 0

    return {
        "readiness_score": pct,
        "points": score,
        "max_points": max_score,
        "checks": checks,
        "gaps": [c["name"] for c in checks if not c["pass"]],
    }
