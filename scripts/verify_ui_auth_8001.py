"""Simulate frontend authApi.js against :8001 (same as browser login flow)."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8001"


def load_password() -> str:
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("PUBLIC_ACCESS_CODE="):
            return line.split("=", 1)[1].strip()
    return ""


def main() -> int:
    pwd = load_password()
    body = json.dumps({"email": "ui-smoke@test.com", "password": pwd}).encode()
    login_req = urllib.request.Request(
        f"{BASE}/api/auth/login",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    login = json.loads(urllib.request.urlopen(login_req).read())
    token = login["access_token"]
    print("login: token length", len(token), "user", login["user"]["email"])

    me_req = urllib.request.Request(
        f"{BASE}/api/auth/me",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    me = json.loads(urllib.request.urlopen(me_req).read())
    print("me:", me["user"]["email"], me["status"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print("HTTP", exc.code, exc.read().decode())
        raise SystemExit(1)
