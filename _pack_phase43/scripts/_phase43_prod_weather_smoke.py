"""Production smoke: weather_intelligence on predict payload — Phase 43."""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from worldcup_predictor.api.main import app
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow
from worldcup_predictor.auth.passwords import hash_password

client = TestClient(app)
settings = get_settings()

print("weather_configured=", settings.weather_provider_configured)
assert settings.weather_provider_configured, "WEATHER_API_KEY not loaded in process"

# Pick a fixture with a real venue city when possible
fixture_id = 1489393

if postgres_configured():
    email = f"phase43-{uuid.uuid4().hex[:8]}@test.local"
    pwd = "Phase43-Weather-Smoke!"
    with saas_uow() as uow:
        uow.users.create(email=email, password_hash=hash_password(pwd), email_verified=True)
    login = client.post("/api/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200, login.text
    token = login.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
else:
    headers = {}

resp = client.get(f"/api/predict/{fixture_id}", headers=headers)
print("predict_status=", resp.status_code)
assert resp.status_code == 200, resp.text[:500]
payload = resp.json()
assert payload.get("status") == "ok", payload.get("message")

wx = payload.get("weather_intelligence")
assert isinstance(wx, dict), "weather_intelligence missing"
print("weather_available=", wx.get("available"))
print("weather_risk=", wx.get("weather_risk_level"))
print("weather_source=", wx.get("source"))

body = json.dumps(payload)
assert settings.weather_api_key not in body
assert "WEATHER_API_KEY" not in body

if wx.get("available"):
    for key in ("temperature_c", "weather_impact_score", "weather_risk_level", "weather_summary"):
        assert key in wx, f"missing {key}"
else:
    print("weather_unavailable_safe_fallback=ok")

print("WEATHER_SMOKE_PASS")
