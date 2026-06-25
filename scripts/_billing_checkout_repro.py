#!/usr/bin/env python3
"""Reproduce billing checkout as a free test user — no secrets printed."""
from __future__ import annotations

import json
import sys
import uuid

from fastapi.testclient import TestClient

from worldcup_predictor.api.main import app
from worldcup_predictor.auth.passwords import hash_password
from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

if not postgres_configured():
    print("postgres_not_configured")
    sys.exit(1)

email = f"billing-audit-{uuid.uuid4().hex[:8]}@test.local"
password = "Billing-Audit-Pass1!"

with saas_uow() as uow:
    uow.users.create(email=email, password_hash=hash_password(password), email_verified=True)

client = TestClient(app)
login = client.post("/api/auth/login", json={"email": email, "password": password})
print("login_status", login.status_code)
token = login.json().get("access_token")
headers = {"Authorization": f"Bearer {token}"}

readiness = client.get("/api/billing/readiness", headers=headers)
print("readiness_status", readiness.status_code)
print("readiness", json.dumps(readiness.json(), indent=2))

legacy = client.post("/api/billing/checkout", headers=headers)
print("legacy_checkout_status", legacy.status_code)
print("legacy_checkout", json.dumps(legacy.json(), indent=2))

checkout = client.post("/api/billing/create-checkout-session", headers=headers, json={"plan": "starter"})
print("create_checkout_status", checkout.status_code)
body = checkout.json()
safe = body
if "checkout_url" in safe and safe["checkout_url"]:
    safe = dict(safe)
    safe["checkout_url"] = safe["checkout_url"][:60] + "..."
print("create_checkout", json.dumps(safe, indent=2))

# Pro user downgrade block
with saas_uow() as uow:
    from worldcup_predictor.database.postgres.enums import SubscriptionPlan, SubscriptionStatus

    uid = uow.users.get_by_email(email).id
    sub = uow.subscriptions.get_or_create_free(uid)
    uow.subscriptions.update_plan(uid, SubscriptionPlan.PRO, status=SubscriptionStatus.ACTIVE)

checkout_pro = client.post("/api/billing/create-checkout-session", headers=headers, json={"plan": "starter"})
print("pro_user_starter_status", checkout_pro.status_code)
print("pro_user_starter", json.dumps(checkout_pro.json(), indent=2))

print("test_email", email)
