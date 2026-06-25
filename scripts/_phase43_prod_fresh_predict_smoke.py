"""Force-refresh predict and verify weather_intelligence — Phase 43 prod smoke."""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from worldcup_predictor.api.main import app
from worldcup_predictor.auth.passwords import hash_password
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.saas_factory import saas_uow

client = TestClient(app)
settings = get_settings()
assert settings.weather_provider_configured

email = f"phase43fresh-{uuid.uuid4().hex[:8]}@test.local"
pwd = "Phase43-Fresh-Pass!"
with saas_uow() as uow:
    uow.users.create(email=email, password_hash=hash_password(pwd), email_verified=True)

login = client.post("/api/auth/login", json={"email": email, "password": pwd})
token = login.json().get("access_token")
headers = {"Authorization": f"Bearer {token}"}

resp = client.get("/api/predict/1489393?force_refresh=true", headers=headers)
print("status=", resp.status_code)
assert resp.status_code == 200, resp.text[:400]
payload = resp.json()
wx = payload.get("weather_intelligence") or {}
print("weather_available=", wx.get("available"))
print("weather_risk=", wx.get("weather_risk_level"))
print("weather_temp=", wx.get("temperature_c"))
print("weather_source=", wx.get("source"))
body = json.dumps(payload)
assert settings.weather_api_key not in body
assert "WEATHER_API_KEY" not in body
if wx.get("available"):
    print("FRESH_WEATHER_AVAILABLE_PASS")
else:
    print("FRESH_WEATHER_FALLBACK_OK")
