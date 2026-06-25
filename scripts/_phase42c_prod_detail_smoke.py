"""Authenticated production smoke for Phase 42C history detail."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from worldcup_predictor.api.main import app
from worldcup_predictor.auth.passwords import hash_password
from worldcup_predictor.database.postgres.enums import Prediction1x2
from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

client = TestClient(app)

if not postgres_configured():
    print("DETAIL_SMOKE_SKIP postgres not configured")
    raise SystemExit(0)

email = f"deploy-smoke-{uuid.uuid4().hex[:8]}@test.local"
pwd = "Deploy42C-Smoke!"
with saas_uow() as uow:
    user = uow.users.create(email=email, password_hash=hash_password(pwd), email_verified=True)
    row = uow.prediction_history.add(
        user.id,
        fixture_id=777042,
        home_team="Smoke Home",
        away_team="Smoke Away",
        prediction_1x2=Prediction1x2.HOME,
        league="World Cup 2026",
        confidence=Decimal("71"),
    )
    entry_id = str(row.id)

login = client.post("/api/auth/login", json={"email": email, "password": pwd})
assert login.status_code == 200, login.text
token = login.json().get("access_token")
headers = {"Authorization": f"Bearer {token}"}

detail = client.get(f"/api/history/{entry_id}", headers=headers)
assert detail.status_code == 200, detail.text
payload = detail.json()
assert payload.get("match_name") == "Smoke Home vs Smoke Away"
assert payload.get("prediction_date") is not None
assert payload.get("summary", {}).get("confidence") == 71.0
assert len(payload.get("prediction", {}).get("markets", [])) >= 1
assert payload.get("evaluation", {}).get("result_status") in {"correct", "wrong", "pending", "unknown"}
assert "withheld_markets" in (payload.get("consistency") or {})

print("DETAIL_SMOKE_PASS")
print("entry_id=", entry_id)
print("match_name=", payload.get("match_name"))
print("prediction_date=", payload.get("prediction_date"))
print("confidence=", payload.get("summary", {}).get("confidence"))
print("markets_count=", len(payload.get("prediction", {}).get("markets", [])))
print("eval_status=", payload.get("evaluation", {}).get("result_status"))
