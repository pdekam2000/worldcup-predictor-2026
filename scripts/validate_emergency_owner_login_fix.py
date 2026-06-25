#!/usr/bin/env python3
"""Emergency owner login validation (production-safe, no password logging)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

from sqlalchemy import text

from worldcup_predictor.database.postgres.session import get_postgres_engine

BASE = os.environ.get("VALIDATION_BASE", "https://footballpredictor.it.com")
EMAIL = os.environ.get("OWNER_EMAIL", "kamangar.pedram@gmail.com")
PW_FILE = os.environ.get("PW_FILE", "/root/.wcp_phase41c_owner_login.txt")


def curl_json(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict | None]:
    cmd = ["curl", "-sS", "-w", "%{http_code}", "-o", "/tmp/em_val_body.json", "-X", method, f"{BASE}{path}"]
    cmd += ["-H", "Accept: application/json"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    code_str = subprocess.check_output(cmd, text=True).strip()
    try:
        code = int(code_str)
    except ValueError:
        code = 0
    try:
        payload = json.loads(Path("/tmp/em_val_body.json").read_text())
    except Exception:
        payload = None
    return code, payload


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    pwd = Path(PW_FILE).read_text().strip("\r\n")
    engine = get_postgres_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT email, role::text, email_verified, is_active, is_banned "
                "FROM users WHERE lower(email)=lower(:e)"
            ),
            {"e": EMAIL},
        ).fetchone()

    checks.append(("owner_row_exists", row is not None, str(row)))
    if row:
        checks.append(("owner_role", row[1] == "owner", row[1]))
        checks.append(("email_verified", bool(row[2]) is True, str(row[2])))
        checks.append(("is_active", bool(row[3]) is True, str(row[3])))
        checks.append(("not_banned", bool(row[4]) is False, str(row[4])))

    cfg_code, cfg = curl_json("GET", "/api/auth/config")
    checks.append(("auth_config_200", cfg_code == 200, str(cfg_code)))

    login_code, login = curl_json("POST", "/api/auth/login", {"email": EMAIL, "password": pwd})
    token = (login or {}).get("access_token") if login else None
    role = ((login or {}).get("user") or {}).get("role")
    checks.append(("owner_login_200", login_code == 200, str(login_code)))
    checks.append(("owner_role_in_jwt", role == "owner", str(role)))
    checks.append(("owner_token_issued", bool(token), "yes" if token else "no"))

    if token:
        ov_code, _ = curl_json("GET", "/api/owner/overview", token=token)
        checks.append(("owner_overview_200", ov_code == 200, str(ov_code)))

    with engine.connect() as conn:
        free = conn.execute(
            text("SELECT email FROM users WHERE role::text IN ('free_user','user') LIMIT 1")
        ).fetchone()
    if free and token:
        # API owner guard: use owner token but simulate non-owner by calling with forged expectation
        # Instead verify owner route rejects via deps — test /api/owner with no token => 401
        unauth_code, _ = curl_json("GET", "/api/owner/overview")
        checks.append(("owner_api_unauth_401", unauth_code == 401, str(unauth_code)))

    bad_code, _ = curl_json("POST", "/api/auth/login", {"email": EMAIL, "password": "definitely-wrong-password"})
    checks.append(("bad_password_401", bad_code == 401, str(bad_code)))

    # Login page serves SPA shell
    html_code = int(subprocess.check_output(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", f"{BASE}/login"], text=True
    ).strip())
    checks.append(("login_page_200", html_code == 200, str(html_code)))

    owner_login_code = int(subprocess.check_output(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", f"{BASE}/owner-login"], text=True
    ).strip())
    checks.append(("owner_login_page_200", owner_login_code == 200, str(owner_login_code)))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name} ({detail})")
    print(f"SUMMARY {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
