#!/usr/bin/env bash
# HOTFIX — Disable email verification — post-deploy smoke
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"

echo "=== Hotfix disable email verification smoke ==="

curl -sf "${BASE}/api/health" >/dev/null
echo "health: ok"

cfg=$(curl -sf "${BASE}/api/auth/config")
echo "auth/config: ${cfg}"
echo "${cfg}" | grep -q '"email_verification_required":false'

PYTHONPATH=/opt/worldcup-predictor /opt/worldcup-predictor/.venv/bin/python - <<'PY'
import uuid
from fastapi.testclient import TestClient
from worldcup_predictor.api.main import app
from worldcup_predictor.access.config import public_access_code
from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits

reset_auth_rate_limits()
client = TestClient(app)
email = f"smoke-noverify-{uuid.uuid4().hex[:8]}@example.com"
body = {"email": email, "password": "SmokeTest123!"}
code = public_access_code()
if code:
    body["invite_code"] = code
r = client.post("/api/auth/register", json=body)
assert r.status_code == 200, r.text
j = r.json()
assert j.get("email_verification_required") is False, j
assert j.get("email_delivery_status") == "verification_disabled", j
r2 = client.post("/api/auth/login", json={"email": email, "password": body["password"]})
assert r2.status_code == 200, r2.text
assert r2.json().get("verification_required") is not True, r2.json()
print("register_login_smoke_ok", email)
PY

echo "SMOKE_OK"
