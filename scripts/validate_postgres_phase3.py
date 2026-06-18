"""Validate Phase 3 — SaaS API routes + optional live HTTP checks."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_env(key: str) -> str:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def test_imports() -> list[str]:
    errors: list[str] = []
    try:
        from worldcup_predictor.api.routes.user import router as user_router  # noqa: F401
        from worldcup_predictor.api.routes.admin import router as admin_router  # noqa: F401
        from worldcup_predictor.api.saas_serializers import settings_to_dict  # noqa: F401

        paths = [r.path for r in user_router.routes]
        for expected in ("/user/settings", "/user/dashboard", "/user/favorites"):
            if expected not in paths:
                errors.append(f"missing user route: {expected}")
        print("OK: Phase 3 route modules import")
    except Exception as exc:
        errors.append(f"import: {exc}")
    return errors


def _http_json(method: str, url: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    import urllib.error
    import urllib.request

    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return exc.code, payload


def test_http_api(base: str = "http://127.0.0.1:8001") -> list[str]:
    errors: list[str] = []
    invite = _load_env("PUBLIC_ACCESS_CODE")
    email = f"phase3-{uuid.uuid4().hex[:8]}@test.local"
    password = "TestPass123!"

    status, health = _http_json("GET", f"{base}/api/health")
    if status != 200:
        print(f"SKIP: API not healthy at {base}")
        return errors

    reg_body = {"email": email, "password": password}
    if invite:
        reg_body["invite_code"] = invite
    status, reg = _http_json("POST", f"{base}/api/auth/register", reg_body)
    if status != 200 or not reg.get("access_token"):
        errors.append(f"register failed: {status}")
        return errors
    token = reg["access_token"]
    print("OK: auth register")

    checks: list[tuple[str, str, int, callable]] = [
        ("GET /api/user/settings", "GET", f"{base}/api/user/settings", lambda s, p: s == 200 and p.get("settings")),
        ("PATCH /api/user/settings", "PATCH", f"{base}/api/user/settings", lambda s, p: s == 200),
        ("GET /api/user/dashboard", "GET", f"{base}/api/user/dashboard", lambda s, p: s == 200 and "stats" in p),
        ("GET /api/user/favorites", "GET", f"{base}/api/user/favorites", lambda s, p: s == 200),
        ("POST /api/user/favorites", "POST", f"{base}/api/user/favorites", lambda s, p: s == 200 and p.get("favorite")),
        ("GET /api/user/alerts", "GET", f"{base}/api/user/alerts", lambda s, p: s == 200),
        ("GET /api/user/notifications", "GET", f"{base}/api/user/notifications", lambda s, p: s == 200),
        ("GET /api/user/prediction-history", "GET", f"{base}/api/user/prediction-history", lambda s, p: s == 200),
        ("GET /api/user/subscription", "GET", f"{base}/api/user/subscription", lambda s, p: s == 200 and p.get("subscription")),
    ]

    fav_id = None
    for name, method, url, ok_fn in checks:
        body = None
        if name == "PATCH /api/user/settings":
            body = {"language": "en", "preferences": {"darkMode": True}}
        if name == "POST /api/user/favorites":
            body = {"type": "team", "item_id": "arsenal", "item_name": "Arsenal", "item_meta": "Premier League"}
        status, payload = _http_json(method, url, body, token)
        if name == "POST /api/user/favorites" and payload.get("favorite"):
            fav_id = payload["favorite"].get("id")
        if not ok_fn(status, payload):
            errors.append(f"{name} failed: {status} {payload}")
        else:
            print(f"OK: {name}")

    if fav_id:
        status, _ = _http_json("DELETE", f"{base}/api/user/favorites/{fav_id}", token=token)
        if status != 200:
            errors.append(f"DELETE favorite failed: {status}")
        else:
            print("OK: DELETE /api/user/favorites/{id}")

    status, matches = _http_json("GET", f"{base}/api/matches/upcoming?limit=1")
    if status == 200 and matches.get("matches"):
        fid = matches["matches"][0]["fixture_id"]
        status, pred = _http_json("POST", f"{base}/api/predict/{fid}", token=token)
        if status != 200:
            errors.append(f"predict failed: {status}")
        else:
            print("OK: POST /api/predict/{id} (with auth)")
        status, hist = _http_json("GET", f"{base}/api/user/prediction-history", token=token)
        if status != 200 or not hist.get("history"):
            errors.append("prediction history not recorded after predict")
        else:
            print("OK: prediction history auto-recorded")

    return errors


def main() -> int:
    errors = test_imports()
    errors.extend(test_http_api())

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1
    print("\nPhase 3 validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
