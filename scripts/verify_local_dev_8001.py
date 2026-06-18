"""Local dev verification — API on :8001, simulates frontend auth + data flows."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.getenv("WCP_API_BASE", "http://127.0.0.1:8001")


def load_env_password() -> str:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("PUBLIC_ACCESS_CODE="):
            return line.split("=", 1)[1].strip()
    return ""


def request(method: str, path: str, *, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode()
        try:
            detail = json.loads(payload)
        except json.JSONDecodeError:
            detail = {"detail": payload}
        return exc.code, detail


def main() -> int:
    failures: list[str] = []

    status, health = request("GET", "/api/health")
    print(f"[health] {status} {health}")
    if status != 200 or health.get("status") != "ok":
        failures.append("health")

    pwd = load_env_password()
    if not pwd:
        failures.append("missing PUBLIC_ACCESS_CODE in .env")
        print("FAIL: cannot test login without PUBLIC_ACCESS_CODE")
        return 1

    status, login = request(
        "POST",
        "/api/auth/login",
        body={"email": "dev-verify@local.test", "password": pwd},
    )
    print(f"[login] {status} user={login.get('user', {}).get('email', '?')}")
    token = login.get("access_token") if status == 200 else None
    if not token:
        failures.append("login")

    status, me = request("GET", "/api/auth/me", token=token)
    print(f"[me] {status} status={me.get('status')}")
    if status != 200 or me.get("status") != "ok":
        failures.append("me")

    status, matches = request("GET", "/api/matches/upcoming?limit=3")
    count = len(matches.get("matches", [])) if isinstance(matches, dict) else 0
    print(f"[matches] {status} count={count}")
    if status != 200:
        failures.append("matches")

    fixture_id = None
    if count > 0:
        fixture_id = matches["matches"][0].get("fixture_id")
        print(f"[match sample] fixture_id={fixture_id} {matches['matches'][0].get('home_team')} vs {matches['matches'][0].get('away_team')}")

    if fixture_id:
        status, pred = request("POST", f"/api/predict/{fixture_id}")
        has_pred = isinstance(pred, dict) and pred.get("status") == "ok"
        print(f"[predict] {status} ok={has_pred}")
        if status not in (200, 422) or (status == 200 and not has_pred):
            failures.append("predict")
    else:
        print("[predict] skipped — no upcoming fixtures")

    if failures:
        print(f"\nFAILED: {', '.join(failures)}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
