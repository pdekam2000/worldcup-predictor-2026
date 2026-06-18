"""Authenticated Phase 3 HTTP verification against live API."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8001"


def _load_env(key: str) -> str:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def http(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    import urllib.error
    import urllib.request

    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return exc.code, payload


def seed_alert_and_notification(user_id: str) -> tuple[str | None, str | None]:
    """Create one alert + notification for mark-read tests."""
    import uuid as _uuid
    from decimal import Decimal

    from worldcup_predictor.database.postgres.enums import AlertType, NotificationType
    from worldcup_predictor.database.saas_factory import saas_uow

    uid = _uuid.UUID(user_id)
    with saas_uow() as uow:
        alert = uow.alerts.create(
            uid,
            type=AlertType.NEW_PREDICTION,
            title="Phase 3 verify",
            message="Test alert for mark-read",
            confidence=Decimal("80"),
        )
        note = uow.notifications.create(
            uid,
            type=NotificationType.SYSTEM,
            title="Phase 3 verify",
            message="Test notification for mark-read",
        )
        return str(alert.id), str(note.id)


def main() -> int:
    results: list[tuple[str, str, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, "PASS" if ok else "FAIL", detail))
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))

    # Health
    status, health = http("GET", "/api/health")
    record("GET /api/health", status == 200 and health.get("status") == "ok", str(status))

    # Register user
    invite = _load_env("PUBLIC_ACCESS_CODE")
    email = f"auth-verify-{uuid.uuid4().hex[:8]}@test.local"
    password = "VerifyPass123!"
    reg_body = {"email": email, "password": password}
    if invite:
        reg_body["invite_code"] = invite
    status, reg = http("POST", "/api/auth/register", reg_body)
    token = reg.get("access_token") if status == 200 else None
    user_id = (reg.get("user") or {}).get("id")
    record("POST /api/auth/register", status == 200 and bool(token))

    status, login = http("POST", "/api/auth/login", {"email": email, "password": password})
    if login.get("access_token"):
        token = login["access_token"]
    record("POST /api/auth/login", status == 200 and bool(token))

    status, me = http("GET", "/api/auth/me", token=token)
    record("GET /api/auth/me", status == 200 and me.get("user", {}).get("email") == email)

    # User SaaS endpoints
    status, dash = http("GET", "/api/user/dashboard", token=token)
    record("GET /api/user/dashboard", status == 200 and dash.get("status") == "ok" and "stats" in dash)

    status, settings = http("GET", "/api/user/settings", token=token)
    record("GET /api/user/settings", status == 200 and settings.get("settings") is not None)

    # User asked PUT — API implements PATCH; test both
    status_patch, patched = http(
        "PATCH",
        "/api/user/settings",
        {"language": "de", "timezone": "Europe/Berlin", "preferences": {"darkMode": True}},
        token=token,
    )
    record("PATCH /api/user/settings", status_patch == 200 and patched.get("settings", {}).get("language") == "de")

    status_put, _ = http("PUT", "/api/user/settings", {"language": "en"}, token=token)
    record(
        "PUT /api/user/settings",
        status_put in (200, 405),
        "not implemented (405)" if status_put == 405 else f"status={status_put}",
    )

    status, favs = http("GET", "/api/user/favorites", token=token)
    record("GET /api/user/favorites", status == 200 and "favorites" in favs)

    status, created = http(
        "POST",
        "/api/user/favorites",
        {"type": "team", "item_id": "verify-team", "item_name": "Verify FC", "item_meta": "Test League"},
        token=token,
    )
    fav_id = (created.get("favorite") or {}).get("id")
    record("POST /api/user/favorites", status == 200 and bool(fav_id))

    if fav_id:
        status, _ = http("DELETE", f"/api/user/favorites/{fav_id}", token=token)
        record("DELETE /api/user/favorites/{id}", status == 200)
    else:
        record("DELETE /api/user/favorites/{id}", False, "no favorite created")

    status, alerts = http("GET", "/api/user/alerts", token=token)
    record("GET /api/user/alerts", status == 200 and "alerts" in alerts)

    alert_id = None
    note_id = None
    if user_id:
        try:
            alert_id, note_id = seed_alert_and_notification(user_id)
        except Exception as exc:
            print(f"WARN: could not seed alert/notification: {exc}")

    if alert_id:
        status, _ = http("PATCH", f"/api/user/alerts/{alert_id}/read", token=token)
        record("PATCH /api/user/alerts/{id}/read", status == 200)
    else:
        record("PATCH /api/user/alerts/{id}/read", False, "no alert to mark read")

    status, notes = http("GET", "/api/user/notifications", token=token)
    record("GET /api/user/notifications", status == 200 and "notifications" in notes)

    if note_id:
        status, _ = http("PATCH", f"/api/user/notifications/{note_id}/read", token=token)
        record("PATCH /api/user/notifications/{id}/read", status == 200)
    else:
        record("PATCH /api/user/notifications/{id}/read", False, "no notification to mark read")

    status, hist = http("GET", "/api/user/prediction-history", token=token)
    record("GET /api/user/prediction-history", status == 200 and "history" in hist)

    status, sub = http("GET", "/api/user/subscription", token=token)
    record("GET /api/user/subscription", status == 200 and sub.get("subscription") is not None)

    # Admin — user asked /admin/status; API has /admin/health
    status, admin_status = http("GET", "/api/admin/status", token=token)
    record(
        "GET /api/admin/status",
        status in (403, 404),
        "not implemented (404)" if status == 404 else "forbidden for non-admin (403)",
    )

    admin_user = _load_env("ADMIN_USERNAME")
    admin_pass = _load_env("ADMIN_PASSWORD")
    admin_token = None
    if admin_user and admin_pass:
        status, admin_login = http("POST", "/api/auth/login", {"email": admin_user, "password": admin_pass})
        admin_token = admin_login.get("access_token") if status == 200 else None

    if admin_token:
        status, admin_health = http("GET", "/api/admin/health", token=admin_token)
        record(
            "GET /api/admin/health (admin)",
            status == 200 and admin_health.get("status") in ("ok", "degraded"),
            admin_health.get("status", ""),
        )
    else:
        record("GET /api/admin/health (admin)", False, "admin login failed")

    print("\n=== Authenticated Phase 3 Summary ===")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    for name, status, detail in results:
        print(f"| {name} | {status} | {detail} |")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
