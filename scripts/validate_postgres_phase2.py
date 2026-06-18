"""Validate Phase 2 — PostgreSQL JWT auth (imports + optional live API)."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_env_password(key: str) -> str:
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
        from worldcup_predictor.auth.passwords import hash_password, verify_password  # noqa: F401
        from worldcup_predictor.auth.jwt_tokens import create_access_token, decode_access_token  # noqa: F401
        from worldcup_predictor.api.web_auth import login_with_password, register_with_password  # noqa: F401

        hashed = hash_password("test-password-123")
        if not verify_password("test-password-123", hashed):
            errors.append("bcrypt verify failed")
        if verify_password("wrong", hashed):
            errors.append("bcrypt should reject wrong password")
        print("OK: password hashing")
    except Exception as exc:
        errors.append(f"import/hash test: {exc}")
    return errors


def test_repository_flow() -> list[str]:
    from worldcup_predictor.api.web_auth import (
        issue_access_token,
        login_with_password,
        register_with_password,
        resolve_bearer_token,
    )
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.postgres.session import ping_postgres, reset_postgres_engine
    from worldcup_predictor.database.saas_factory import saas_uow

    get_settings.cache_clear()
    reset_postgres_engine()
    from worldcup_predictor.database.postgres.session import ping_postgres, reset_postgres_engine
    from worldcup_predictor.database.saas_factory import saas_uow

    errors: list[str] = []
    settings = get_settings()
    if not settings.postgres_configured:
        print("SKIP: DATABASE_URL not set")
        return errors
    if not ping_postgres():
        print("SKIP: PostgreSQL not reachable (start DB and run: alembic upgrade head)")
        return errors

    invite = _load_env_password("PUBLIC_ACCESS_CODE")
    email = f"phase2-{uuid.uuid4().hex[:8]}@test.local"
    password = "TestPass123!"

    reset_postgres_engine()
    try:
        profile, err = register_with_password(
            email=email,
            password=password,
            invite_code=invite or None,
        )
        if err or profile is None:
            errors.append(f"register failed: {err}")
            return errors
        print(f"OK: register user={profile.email}")

        token = issue_access_token(profile)
        resolved = resolve_bearer_token(token)
        if resolved is None or resolved.email != email:
            errors.append("JWT resolve failed")
        else:
            print("OK: JWT issue + resolve")

        with saas_uow() as uow:
            settings_row = uow.settings.get(profile.id)
            sub_row = uow.subscriptions.get_for_user(profile.id)
            if settings_row is None:
                errors.append("user_settings not created")
            else:
                print("OK: user_settings provisioned")
            if sub_row is None:
                errors.append("subscription not created")
            else:
                print(f"OK: subscription plan={sub_row.plan.value}")

        logged, login_err = login_with_password(email=email, password=password)
        if login_err or logged is None:
            errors.append(f"login failed: {login_err}")
        else:
            print("OK: login with bcrypt password")

        bad, _ = login_with_password(email=email, password="wrong-password")
        if bad is not None:
            errors.append("login should fail for wrong password")
        else:
            print("OK: login rejects wrong password")

    except Exception as exc:
        errors.append(f"repository flow: {exc}")
    finally:
        reset_postgres_engine()

    return errors


def test_http_api(base: str = "http://127.0.0.1:8001") -> list[str]:
    import urllib.error
    import urllib.request

    errors: list[str] = []
    invite = _load_env_password("PUBLIC_ACCESS_CODE")
    email = f"http-{uuid.uuid4().hex[:8]}@test.local"
    password = "TestPass123!"

    def post(path: str, body: dict) -> tuple[int, dict]:
        req = urllib.request.Request(
            f"{base}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode()
            try:
                detail = json.loads(payload)
            except json.JSONDecodeError:
                detail = {"detail": payload}
            return exc.code, detail

    try:
        urllib.request.urlopen(f"{base}/api/health", timeout=5)
    except Exception:
        print(f"SKIP: HTTP API not running at {base}")
        return errors

    body = {"email": email, "password": password}
    if invite:
        body["invite_code"] = invite
    status, reg = post("/api/auth/register", body)
    if status != 200 or not reg.get("access_token"):
        errors.append(f"HTTP register failed: {status} {reg}")
        return errors
    print("OK: HTTP register")

    token = reg["access_token"]
    me_req = urllib.request.Request(
        f"{base}/api/auth/me",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(me_req, timeout=10) as resp:
        me = json.loads(resp.read().decode())
    if me.get("status") != "ok" or me.get("user", {}).get("email") != email:
        errors.append(f"HTTP /me failed: {me}")
    else:
        print("OK: HTTP /api/auth/me")

    status, login = post("/api/auth/login", {"email": email, "password": password})
    if status != 200 or not login.get("access_token"):
        errors.append(f"HTTP login failed: {status} {login}")
    else:
        print("OK: HTTP login")

    return errors


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--no-http", action="store_true", help="Skip live HTTP API checks")
    args = parser.parse_args()

    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()
    errors = test_imports()
    errors.extend(test_repository_flow())
    if not args.no_http:
        errors.extend(test_http_api())

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1
    print("\nPhase 2 validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
