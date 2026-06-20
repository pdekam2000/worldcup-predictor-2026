#!/usr/bin/env bash
# SaaS smoke tests — no secrets printed.
set -uo pipefail
APP="/opt/worldcup-predictor"
IP="91.107.188.229"
BASE="http://127.0.0.1:8000"
PUB="http://$IP"

pass() { printf 'PASS\t%s\n' "$1"; }
fail() { printf 'FAIL\t%s\n' "$1"; }

cd "$APP"
set -a && source .env.production && set +a

.venv/bin/python <<'PY'
import json
import os
import secrets
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
PUB = f"http://{os.environ.get('SERVER_IP', '91.107.188.229')}"


def req(method, url, data=None, headers=None):
    body = None
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    if data is not None:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode())
        except Exception:
            detail = {"detail": str(e)}
        return e.code, detail


def check(name, ok, detail=""):
    if ok:
        print(f"PASS\t{name}")
    else:
        print(f"FAIL\t{name}: {detail}")
        return False
    return True


ok = True
invite = (os.environ.get("PUBLIC_ACCESS_CODE") or "").strip()
email = f"phase2test_{secrets.token_hex(4)}@example.com"
password = f"TestPass_{secrets.token_hex(8)}!"

# Register
payload = {"email": email, "password": password}
if invite:
    payload["invite_code"] = invite
code, reg = req("POST", f"{BASE}/api/auth/register", payload)
ok &= check("register", code in (200, 201), str(reg)[:120])

token = reg.get("access_token") if code in (200, 201) else None
if not token:
    # try login if user exists
    code, login = req("POST", f"{BASE}/api/auth/login", {"email": email, "password": password})
    token = login.get("access_token") if code == 200 else None

if token:
    auth = {"Authorization": f"Bearer {token}"}
    code, me = req("GET", f"{BASE}/api/auth/me", headers=auth)
    ok &= check("/api/auth/me", code == 200 and "user" in me, str(me)[:120])

    code, dash = req("GET", f"{BASE}/api/user/dashboard", headers=auth)
    ok &= check("dashboard API", code == 200, str(dash)[:80])

    code, matches = req("GET", f"{BASE}/api/matches/upcoming?limit=3", headers=auth)
    ok &= check("match center /api/matches/upcoming", code == 200, str(matches)[:80])

    fixture_id = None
    if code == 200:
        items = matches.get("matches") or matches.get("fixtures") or []
        if items and isinstance(items, list):
            fixture_id = items[0].get("fixture_id")

    if fixture_id:
        code, pred = req("POST", f"{BASE}/api/predict/{fixture_id}", headers=auth)
        ok &= check("prediction detail POST /api/predict/{id}", code == 200, str(pred)[:80])
    else:
        ok &= check("prediction detail", False, "no fixture_id from upcoming matches")

    # Public via nginx
    code, pub_health = req("GET", f"{PUB}/api/health")
    ok &= check("public /api/health via nginx", code == 200)
else:
    ok &= check("auth flow", False, f"register/login failed: {reg if 'reg' in dir() else ''}")

sys.exit(0 if ok else 1)
PY
exit $?
