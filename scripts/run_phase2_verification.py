"""End-to-end Phase 2 verification — embedded PostgreSQL + FastAPI smoke tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

API_BASE = os.getenv("WCP_VERIFY_API", "http://127.0.0.1:8001")


def _load_env_key(key: str) -> str:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def _set_env(key: str, value: str) -> None:
    os.environ[key] = value


def _http_json(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return exc.code, payload


def main() -> int:
    results: list[tuple[str, str, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, "PASS" if ok else "FAIL", detail))
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))

    # 1. Start embedded PostgreSQL
    from local_postgres import start_server

    db_url = start_server()
    _set_env("DATABASE_URL", db_url)
    if not os.getenv("JWT_SECRET"):
        _set_env("JWT_SECRET", _load_env_key("JWT_SECRET") or "dev-phase2-jwt-secret-change-in-production")

    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()

    from worldcup_predictor.database.postgres.session import ping_postgres, reset_postgres_engine

    reset_postgres_engine()
    record("PostgreSQL reachable", ping_postgres(), db_url)

    # 2. Alembic migrate
    migrate = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    record("alembic upgrade head", migrate.returncode == 0, migrate.stderr.strip()[:200] or "ok")

    # 3. Stop stale API on 8001 before validation / fresh start
    for line in subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout.splitlines():
        if ":8001" in line and "LISTENING" in line:
            pid = line.split()[-1]
            if pid.isdigit():
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)

    # 4. Phase 2 validate script (repository only — HTTP tested after API starts)
    validate = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_postgres_phase2.py"), "--no-http"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    record("validate_postgres_phase2.py", validate.returncode == 0, validate.stdout.strip()[-200:])

    # 5. Start API
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "worldcup_predictor.api.main:app", "--host", "127.0.0.1", "--port", "8001"],
        cwd=str(ROOT),
        env=os.environ.copy(),
    )
    time.sleep(4)

    try:
        status, health = _http_json("GET", "/api/health")
        record("GET /api/health", status == 200 and health.get("status") == "ok")

        invite = _load_env_key("PUBLIC_ACCESS_CODE")
        email = f"verify-{uuid.uuid4().hex[:8]}@test.local"
        password = "VerifyPass123!"
        reg_body = {"email": email, "password": password}
        if invite:
            reg_body["invite_code"] = invite
        status, reg = _http_json("POST", "/api/auth/register", reg_body)
        record("POST /api/auth/register", status == 200 and bool(reg.get("access_token")))

        status, login = _http_json("POST", "/api/auth/login", {"email": email, "password": password})
        token = login.get("access_token") if status == 200 else None
        record("POST /api/auth/login", status == 200 and bool(token))

        status, me = _http_json("GET", "/api/auth/me", token=token)
        record(
            "GET /api/auth/me",
            status == 200 and me.get("status") == "ok" and me.get("user", {}).get("email") == email,
        )

        status, matches = _http_json("GET", "/api/matches/upcoming?limit=10")
        count = len(matches.get("matches", [])) if isinstance(matches, dict) else 0
        record("GET /api/matches/upcoming", status == 200 and count > 0, f"count={count}")

        fixture_id = matches["matches"][0]["fixture_id"] if count else None
        if fixture_id:
            status, pred = _http_json("POST", f"/api/predict/{fixture_id}")
            ok = status == 200 and pred.get("status") == "ok"
            record("POST /api/predict/{id}", ok, f"fixture={fixture_id}")
        else:
            record("POST /api/predict/{id}", False, "no fixtures")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    print("\n=== Phase 2 Verification Summary ===")
    failed = 0
    for name, status, detail in results:
        line = f"| {name} | {status} | {detail} |"
        print(line)
        if status == "FAIL":
            failed += 1

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
