#!/usr/bin/env python3
"""Phase 34 production smoke tests — run on server."""
import json
import os
import sys
import uuid

import urllib.error
import urllib.request

BASE = os.environ.get("SMOKE_BASE", "http://127.0.0.1:8000")


def req(method, path, token=None, body=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = raw
        return e.code, payload


def main():
    results = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    # Health
    code, health = req("GET", "/api/health")
    check("public_health", code == 200 and health.get("status") == "ok", str(health))

    admin_user = os.environ.get("ADMIN_USERNAME", "admin")
    admin_pass = os.environ.get("ADMIN_PASSWORD", "")

    if not admin_pass:
        # load from .env.production
        env_path = "/opt/worldcup-predictor/.env.production"
        if os.path.isfile(env_path):
            for line in open(env_path):
                line = line.strip()
                if line.startswith("ADMIN_USERNAME="):
                    admin_user = line.split("=", 1)[1].strip().strip('"').strip("'")
                if line.startswith("ADMIN_PASSWORD="):
                    admin_pass = line.split("=", 1)[1].strip().strip('"').strip("'")

    code, login = req("POST", "/api/auth/login", body={"email": admin_user, "password": admin_pass})
    token = (login or {}).get("access_token") or (login or {}).get("token")
    check("admin_login", code == 200 and bool(token), f"http={code}")

    if token:
        code, summary = req("GET", "/api/admin/accuracy/summary", token=token)
        check("admin_accuracy_summary", code == 200 and "statistics" in (summary or {}), f"http={code}")

        code, evals = req("GET", "/api/admin/accuracy/evaluations?limit=5", token=token)
        rows = (evals or {}).get("rows") or []
        check("admin_accuracy_evaluations", code == 200, f"rows={len(rows)}")

        if rows:
            fid = rows[0].get("fixture_id")
            code, insp = req("GET", f"/api/admin/accuracy/fixtures/{fid}", token=token)
            check("match_inspector", code == 200 and (insp or {}).get("stored_prediction") is not None, f"fixture={fid}")

        code, dash = req("GET", "/api/admin/learning/dashboard", token=token)
        check("learning_dashboard", code == 200 and (dash or {}).get("status") == "ok", f"http={code}")

        code, gen = req("POST", "/api/admin/learning/reports/generate", token=token)
        check("learning_report_generate", code == 200 and (gen or {}).get("report_id") is not None, f"http={code}")

        code, quota_admin = req("GET", "/api/user/quota", token=token)
        check("admin_quota_bypass", code == 200 and (quota_admin or {}).get("bypass") is True, str(quota_admin))

    # Non-admin quota path — use random uuid user via direct service
    sys.path.insert(0, "/opt/worldcup-predictor")
    from worldcup_predictor.subscription.quota_service import get_user_quota_status, record_prediction_usage

    test_uid = str(uuid.uuid4())
    q0 = get_user_quota_status(test_uid, role="user")
    check("free_quota_initial", q0.allowed and q0.daily_limit == 1)
    record_prediction_usage(test_uid, 888001)
    q1 = get_user_quota_status(test_uid, role="user")
    check("free_quota_blocked", not q1.allowed and q1.used_today == 1)
    q_reuse = get_user_quota_status(test_uid, role="user", fixture_id=888001)
    check("same_fixture_reuse_allowed", q_reuse.allowed)

    # Cache reuse — no auth required for GET cached
    code, cached = req("GET", "/api/predict/1539007?competition=world_cup_2026&season=2026")
    check("stored_prediction_get", code == 200 and (cached or {}).get("status") == "ok", f"http={code}")

    code, audit = req("GET", "/api/admin/accuracy/audit", token=token) if token else (0, {})
    check("accuracy_audit", code == 200 and (audit or {}).get("healthy") is True, str(audit))

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\nSmoke: {passed}/{len(results)} PASS")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
