#!/usr/bin/env python3
"""Production billing config audit — no secrets printed."""
import os
import sys

os.environ.setdefault("APP_ENV", "production")
sys.path.insert(0, "/opt/worldcup-predictor")

from worldcup_predictor.billing.billing_service import BillingService
from worldcup_predictor.config.settings import get_settings

s = get_settings()
bs = BillingService(s)
r = bs.readiness()

keys = {
    "STRIPE_SECRET_KEY": s.stripe_secret_key_configured,
    "STRIPE_WEBHOOK_SECRET": s.stripe_webhook_secret_configured,
    "STRIPE_STARTER_PRICE_ID": s.stripe_starter_price_configured,
    "STRIPE_PRO_PRICE_ID": s.stripe_pro_price_configured,
    "STRIPE_SUCCESS_URL": s.stripe_success_url_configured,
    "STRIPE_CANCEL_URL": s.stripe_cancel_url_configured,
    "STRIPE_MODE": bool(s.stripe_mode_normalized in ("test", "live")),
}
for k, ok in keys.items():
    print(f"{k}={'present' if ok else 'missing'}")

print("stripe_mode", s.stripe_mode_normalized)
print("stripe_package_available", r.stripe_package_available)
print("checkout_enabled", r.checkout_enabled)
print("starter_price_configured", r.starter_price_configured)
print("pro_price_configured", r.pro_price_configured)
print("success_url_configured", r.success_url_configured)
print("cancel_url_configured", r.cancel_url_configured)
print("webhook_secret_configured", r.webhook_secret_configured)
print("readiness_message", r.message)
