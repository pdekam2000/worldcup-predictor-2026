#!/usr/bin/env bash
# Verify SaaS flows over HTTPS domain.
set -uo pipefail
DOMAIN="${1:-footballpredictor.it.com}"
BASE="https://$DOMAIN"

pass() { printf 'PASS\t%s\n' "$1"; }
fail() { printf 'FAIL\t%s\n' "$1"; }

cd /opt/worldcup-predictor
set -a && source .env.production && set +a

/opt/worldcup-predictor/.venv/bin/python <<PY
import json
import os
import secrets
import ssl
import sys
import urllib.error
import urllib.request

DOMAIN = "$DOMAIN"
BASE = f"https://{DOMAIN}"
ctx = ssl.create_default_context()


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
        with urllib.request.urlopen(r, timeout=60, context=ctx) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode())
        except Exception:
            detail = {"detail": str(e)}
        return e.code, detail


def check(name, ok, detail=""):
    global all_ok
    if ok:
        print(f"PASS\t{name}")
    else:
        print(f"FAIL\t{name}: {detail}")
        all_ok = False


all_ok = True
invite = (os.environ.get("PUBLIC_ACCESS_CODE") or "").strip()
email = f"ssltest_{secrets.token_hex(4)}@example.com"
password = f"TestPass_{secrets.token_hex(8)}!"

payload = {"email": email, "password": password}
if invite:
    payload["invite_code"] = invite

code, reg = req("POST", f"{BASE}/api/auth/register", payload)
check("register", code in (200, 201), str(reg)[:120])
token = reg.get("access_token") if code in (200, 201) else None

if token:
    auth = {"Authorization": f"Bearer {token}"}
    code, me = req("GET", f"{BASE}/api/auth/me", headers=auth)
    check("login/session (/api/auth/me)", code == 200)

    code, dash = req("GET", f"{BASE}/api/user/dashboard", headers=auth)
    check("dashboard", code == 200)

    code, matches = req("GET", f"{BASE}/api/matches/upcoming?limit=3", headers=auth)
    check("match center", code == 200)

    fixture_id = None
    if code == 200:
        items = matches.get("matches") or matches.get("fixtures") or []
        if items:
            fixture_id = items[0].get("fixture_id")

    if fixture_id:
        code, pred = req("POST", f"{BASE}/api/predict/{fixture_id}", headers=auth)
        check("prediction detail", code == 200, str(pred)[:80])
    else:
        check("prediction detail", False, "no fixtures")
else:
    check("auth", False, str(reg)[:120])

for route in ["/login", "/dashboard", "/matches"]:
    code, _ = req("GET", f"{BASE}{route}")
    # SPA returns HTML 200
    check(f"SPA route {route}", code == 200)

sys.exit(0 if all_ok else 1)
PY
