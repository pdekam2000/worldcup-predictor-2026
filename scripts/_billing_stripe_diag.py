#!/usr/bin/env python3
"""Diagnose Stripe InvalidRequestError — message only, no secrets."""
import os
import sys

os.environ.setdefault("APP_ENV", "production")
sys.path.insert(0, "/opt/worldcup-predictor")

from worldcup_predictor.config.settings import get_settings

s = get_settings()
import stripe

stripe.api_key = s.stripe_secret_key.strip()
price_id = s.stripe_starter_price_id.strip()
print("mode", s.stripe_mode_normalized)
print("price_id_prefix", price_id[:12] + "..." if price_id else "missing")

try:
    cust = stripe.Customer.create(email="billing-diag@test.local", metadata={"diag": "1"})
    print("customer_ok", cust.id[:10] + "...")
    session = stripe.checkout.Session.create(
        customer=cust.id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=s.stripe_success_url.strip(),
        cancel_url=s.stripe_cancel_url.strip(),
        metadata={"requested_plan": "starter"},
    )
    print("session_ok", bool(session.url))
except Exception as exc:
    print("error_type", type(exc).__name__)
    print("error_message", str(exc))
    user_msg = getattr(exc, "user_message", None)
    if user_msg:
        print("user_message", user_msg)
    param = getattr(exc, "param", None)
    if param:
        print("param", param)
