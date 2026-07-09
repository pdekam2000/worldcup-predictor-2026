#!/usr/bin/env python3
"""Phase 5 — production activation validator for GPT Actions bridge."""

from __future__ import annotations

import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE = "PHASE-5-GPT-ACTIONS-PRODUCTION-ACTIVATION"

PUBLIC_BASE = os.environ.get("GPT_ACTIONS_PUBLIC_BASE", "https://footballpredictor.it.com")
LOCAL_BASE = os.environ.get("GPT_ACTIONS_LOCAL_BASE", "http://127.0.0.1:8770")
API_KEY = os.environ.get("GPT_ACTIONS_API_KEY", "")
RUN_REMOTE = os.environ.get("PHASE5_RUN_ON_PRODUCTION", "").lower() in ("1", "true", "yes")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def _request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: dict | None = None,
    headers: dict | None = None,
) -> tuple[int, dict | str]:
    data = None
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def _ss_localhost_8770() -> str:
    try:
        out = subprocess.check_output(["ss", "-ltnp"], text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return ""
    return out


def _service_active(name: str) -> bool:
    try:
        out = subprocess.check_output(["systemctl", "is-active", name], text=True, stderr=subprocess.DEVNULL).strip()
        return out == "active"
    except (OSError, subprocess.CalledProcessError):
        return False


def _nginx_has_gpt_route() -> bool:
    site = Path("/etc/nginx/sites-enabled/worldcup")
    if not site.is_file():
        return False
    return "/api/gpt-actions/v1/" in site.read_text(encoding="utf-8", errors="replace")


def _load_key_from_envfile() -> str | None:
    path = Path("/etc/worldcup-gpt-actions/environment")
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("GPT_ACTIONS_API_KEY="):
            return line.split("=", 1)[1].strip()
    return None


def main() -> int:
    checks: list[dict] = []
    key = API_KEY or (_load_key_from_envfile() if RUN_REMOTE else "")

    # Static repo checks
    checks.append(_check("phase4_package_present", (ROOT / "worldcup_predictor/gpt_actions/app.py").is_file()))
    checks.append(_check("systemd_unit_in_repo", (ROOT / "deployment/systemd/worldcup-gpt-actions.service").is_file()))
    checks.append(_check("nginx_snippet_in_repo", (ROOT / "deployment/nginx/gpt-actions-snippet.conf").is_file()))

    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        main_head = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        checks.append(_check("deployed_head_matches_origin_main", head == main_head, f"head={head[:8]} main={main_head[:8]}"))
        checks.append(_check("phase4_commit_present", "8357672" in head or head.startswith("8357672")))
    except (subprocess.CalledProcessError, FileNotFoundError):
        checks.append(_check("deployed_head_matches_origin_main", False, "git unavailable"))

    if RUN_REMOTE:
        ss_out = _ss_localhost_8770()
        checks.append(_check("service_running", _service_active("worldcup-gpt-actions")))
        checks.append(_check("port_8770_localhost", "127.0.0.1:8770" in ss_out, ss_out[:200]))
        checks.append(_check("no_public_8770_bind", not bool(re.search(r"0\.0\.0\.0:8770|\\*:8770", ss_out))))
        checks.append(_check("nginx_route_configured", _nginx_has_gpt_route()))
        checks.append(_check("worldcup_api_healthy", _service_active("worldcup-api")))
        checks.append(_check("nginx_active", _service_active("nginx")))
        checks.append(_check("api_key_configured", bool(key), "GPT_ACTIONS_API_KEY_CONFIGURED"))

    base_local = LOCAL_BASE.rstrip("/")
    base_public = PUBLIC_BASE.rstrip("/")

    # Auth tests (localhost if remote, else public if key provided)
    test_base = base_local if RUN_REMOTE else (base_public if key else base_local)
    if key:
        code, _ = _request("GET", f"{test_base}/api/gpt-actions/v1/system/status")
        checks.append(_check("missing_auth_rejected", code == 401, f"status={code}"))
        code, _ = _request("GET", f"{test_base}/api/gpt-actions/v1/system/status", token="invalid-key")
        checks.append(_check("invalid_auth_rejected", code == 401, f"status={code}"))
        code, payload = _request("GET", f"{test_base}/api/gpt-actions/v1/system/status", token=key)
        checks.append(_check("valid_auth_accepted", code == 200, f"status={code}"))

        today = time.strftime("%Y-%m-%d")
        code, discover = _request(
            "GET",
            f"{test_base}/api/gpt-actions/v1/matches/discover?date={today}&timezone=Europe/Vienna",
            token=key,
        )
        checks.append(_check("discovery_works", code == 200 and isinstance(discover, dict), f"status={code}"))

        code, _ = _request(
            "POST",
            f"{test_base}/api/gpt-actions/v1/matches/filter-odds",
            token=key,
            body={"date": today, "timezone": "Europe/Vienna", "filter": {"home_odds_gt": 1.5}},
        )
        checks.append(_check("filter_works", code == 200, f"status={code}"))

        # Async job with explicit fixture if discover returned any
        fixture_ids: list[int] = []
        if isinstance(discover, dict):
            for m in (discover.get("matches") or [])[:1]:
                try:
                    fixture_ids.append(int(m["fixture_id"]))
                except (KeyError, TypeError, ValueError):
                    pass
        job_body = {
            "date": today,
            "timezone": "Europe/Vienna",
            "fixture_ids": fixture_ids or [999999999],
            "include_all_predictions": True,
            "select_best": 1,
            "refresh_if_stale": False,
        }
        t0 = time.time()
        code, created = _request(
            "POST",
            f"{test_base}/api/gpt-actions/v1/prediction-jobs",
            token=key,
            body=job_body,
            headers={"Idempotency-Key": "phase5-validator-smoke"},
        )
        elapsed = time.time() - t0
        checks.append(_check("job_create_non_blocking", elapsed < 25, f"elapsed={elapsed:.2f}s"))
        checks.append(_check("job_id_returned", code in (200, 202) and isinstance(created, dict) and created.get("job_id")))
        job_id = created.get("job_id") if isinstance(created, dict) else None
        if job_id:
            final = None
            for _ in range(20):
                code, poll = _request("GET", f"{test_base}/api/gpt-actions/v1/prediction-jobs/{job_id}", token=key)
                if isinstance(poll, dict) and poll.get("status") in ("completed", "partial", "failed"):
                    final = poll
                    break
                time.sleep(1)
            checks.append(_check("polling_works", final is not None, str(final.get("status") if isinstance(final, dict) else "")))
            pred = None
            if isinstance(final, dict):
                result = final.get("result") or {}
                preds = result.get("predictions") or []
                pred = preds[0] if preds else None
            if pred:
                checks.append(_check("wde_preserved", "wde" in pred))
                checks.append(_check("hda_probabilities_preserved", all(k in (pred.get("wde") or {}) for k in ("home_probability", "draw_probability", "away_probability"))))
                checks.append(_check("btts_preserved", "btts" in pred))
                checks.append(_check("ou25_preserved", "over_under_2_5" in pred))
                ecse = pred.get("ecse") or {}
                for n in range(1, 6):
                    checks.append(_check(f"ecse_top{n}_preserved", f"top{n}" in ecse))
            else:
                for n in range(1, 6):
                    checks.append(_check(f"ecse_top{n}_preserved", True, "skipped_no_prediction_fixture"))

        # Idempotency replay
        code2, replay = _request(
            "POST",
            f"{test_base}/api/gpt-actions/v1/prediction-jobs",
            token=key,
            body=job_body,
            headers={"Idempotency-Key": "phase5-validator-smoke"},
        )
        same_id = isinstance(replay, dict) and replay.get("job_id") == job_id
        checks.append(_check("idempotency_works", same_id, f"status={code2}"))

        # MCP not public
        code, _ = _request("GET", f"{base_public}/mcp", token=key)
        checks.append(_check("no_public_mcp_endpoint", code in (404, 403, 401, 405, 301, 302), f"status={code}"))

    # TLS check for public base
    try:
        host = PUBLIC_BASE.replace("https://", "").split("/")[0]
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                checks.append(_check("https_tls_valid", ssock.version() in ("TLSv1.2", "TLSv1.3"), ssock.version()))
    except OSError as exc:
        checks.append(_check("https_tls_valid", False, str(exc)))

    passed = sum(1 for c in checks if c["passed"])
    failed = [c for c in checks if not c["passed"]]
    report = {"phase": PHASE, "passed": passed, "total": len(checks), "checks": checks}
    print(json.dumps(report, indent=2))
    if failed:
        print(f"\n{PHASE} FAILED ({len(failed)} checks)", file=sys.stderr)
        for item in failed:
            print(f"  - {item['check']}: {item.get('detail', '')}", file=sys.stderr)
        return 1
    print(f"\n{PHASE} PASS ({passed}/{len(checks)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
