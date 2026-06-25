#!/usr/bin/env python3
import json
import sys
import uuid
import os
os.environ.setdefault("APP_ENV", "production")
sys.path.insert(0, "/opt/worldcup-predictor")
from fastapi.testclient import TestClient
from worldcup_predictor.api.main import app
from worldcup_predictor.auth.passwords import hash_password
from worldcup_predictor.database.saas_factory import saas_uow

email = f"billing-post-{uuid.uuid4().hex[:8]}@test.local"
pwd = "Billing-Post-Pass1!"
with saas_uow() as uow:
    uow.users.create(email=email, password_hash=hash_password(pwd), email_verified=True)
client = TestClient(app)
login = client.post("/api/auth/login", json={"email": email, "password": pwd})
headers = {"Authorization": f"Bearer {login.json().get('access_token')}"}
r = client.get("/api/billing/readiness", headers=headers).json()
print("readiness", json.dumps({k: r.get(k) for k in ['checkout_enabled','checkout_configured','message','starter_price_configured','pro_price_configured']}, indent=2))
c = client.post("/api/billing/create-checkout-session", headers=headers, json={"plan": "starter"})
print("checkout_status", c.status_code)
print("checkout_body", json.dumps(c.json(), indent=2))
