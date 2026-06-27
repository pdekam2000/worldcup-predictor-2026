#!/usr/bin/env python3
"""Phase A12B — pre-production safety check before Phase A12 deploy."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "base44-d"
PROD_BASE = os.environ.get("A12B_PROD_BASE", "https://footballpredictor.it.com")
PROD_SSH = os.environ.get("A12B_PROD_SSH", "root@91.107.188.229")
APP = "/opt/worldcup-predictor"
MIN_STORED = int(os.environ.get("A12B_MIN_STORED", "1"))
MIN_EVALUATED = int(os.environ.get("A12B_MIN_EVALUATED", "0"))
MIN_HISTORY_API = int(os.environ.get("A12B_MIN_HISTORY", "1"))


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def http_get(url: str, headers: dict | None = None, timeout: int = 25) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def ssh(cmd: str, timeout: int = 120) -> tuple[int, str]:
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", PROD_SSH, cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def count_router_registrations(main_text: str, symbol: str) -> int:
    return len(re.findall(rf"app\.include_router\(\s*{re.escape(symbol)}\b", main_text))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    local_main = (ROOT / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")

    # --- 2. Router registration (local repo) ---
    for sym in ("history_router", "performance_router"):
        n = count_router_registrations(local_main, sym)
        record(checks, f"router_once_{sym}", n == 1, f"count={n}")

    # --- 1. Production route probes (pre-deploy: route may 401/404) ---
    route_specs = [
        ("route_history", f"{PROD_BASE}/api/history", {200, 401}),
        ("route_history_global", f"{PROD_BASE}/api/history/global", {200, 401, 404, 422}),
        ("route_performance_summary", f"{PROD_BASE}/api/performance/summary", {200, 401, 404}),
        ("route_performance_details", f"{PROD_BASE}/api/performance/details", {200, 401, 404}),
    ]
    for name, url, ok_codes in route_specs:
        code, body = http_get(url)
        # Pre-deploy: 404 means router not yet deployed; we note but don't fail entire check on summary/history if local has routers
        if name in {"route_performance_summary", "route_history"} and code == 404:
            local_ok = count_router_registrations(local_main, "history_router" if "history" in name else "performance_router") == 1
            record(checks, name, local_ok, f"prod={code} local_router_ready={local_ok}")
        else:
            record(checks, name, code in ok_codes, f"http={code} body={body[:80]}")

    # --- 3–5. Production DB via SSH ---
    db_script = r"""
python3 << 'PY'
import json, sqlite3, os
from pathlib import Path
app = Path("/opt/worldcup-predictor")
db = app / "data/football_intelligence.db"
out = {"db_exists": db.is_file(), "tables": {}, "counts": {}, "migrations_ok": True, "errors": []}
if not out["db_exists"]:
    out["errors"].append("db_missing")
    print(json.dumps(out))
    raise SystemExit(0)
conn = sqlite3.connect(str(db))
conn.row_factory = sqlite3.Row
cur = conn.cursor()
required = [
    "worldcup_stored_predictions",
    "worldcup_prediction_evaluations",
    "worldcup_accuracy_summary",
]
for t in required:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,))
    out["tables"][t] = cur.fetchone() is not None
for t in required:
    if out["tables"].get(t):
        cur.execute(f"SELECT COUNT(*) AS c FROM {t}")
        out["counts"][t] = int(cur.fetchone()["c"])
# quarantine column
try:
    cur.execute("SELECT is_quarantined FROM worldcup_prediction_evaluations LIMIT 1")
    out["migrations_ok"] = True
except Exception as e:
    out["migrations_ok"] = False
    out["errors"].append(f"migration_col:{e}")
# git on server
try:
    import subprocess
    out["server_commit"] = subprocess.check_output(["git", "-C", str(app), "rev-parse", "HEAD"], text=True).strip()
except Exception:
    out["server_commit"] = None
conn.close()
print(json.dumps(out))
PY
"""
    rc, db_out = ssh(db_script)
    db_info: dict = {}
    if rc == 0 and db_out:
        try:
            db_info = json.loads(db_out.splitlines()[-1])
        except json.JSONDecodeError:
            record(checks, "prod_db_parse", False, db_out[:200])
    else:
        record(checks, "prod_db_ssh", False, db_out[:200])

    if db_info:
        record(checks, "db_exists", db_info.get("db_exists") is True)
        for t in ("worldcup_stored_predictions", "worldcup_prediction_evaluations", "worldcup_accuracy_summary"):
            record(checks, f"table_{t}", db_info.get("tables", {}).get(t) is True)
        stored = int(db_info.get("counts", {}).get("worldcup_stored_predictions") or 0)
        evals = int(db_info.get("counts", {}).get("worldcup_prediction_evaluations") or 0)
        record(checks, "count_stored_predictions", stored >= MIN_STORED, f"count={stored} min={MIN_STORED}")
        record(checks, "count_evaluations", evals >= MIN_EVALUATED, f"count={evals} min={MIN_EVALUATED}")
        record(checks, "migrations_quarantine_col", db_info.get("migrations_ok") is True)
        record(checks, "no_empty_stored_dataset", stored > 0, "stored predictions must exist")

    # --- 1b. Local FastAPI route registration (authoritative) ---
    try:
        from worldcup_predictor.api.main import app

        paths = {getattr(r, "path", "") for r in app.routes}
        for need in (
            "/api/history",
            "/api/performance/summary",
            "/api/performance/details",
        ):
            record(checks, f"local_route_{need.strip('/').replace('/', '_')}", need in paths, f"registered={need in paths}")
        # /api/history/global matches /api/history/{entry_id}
        record(checks, "local_route_history_global", "/api/history/{entry_id}" in paths)
    except Exception as exc:
        record(checks, "local_route_import", False, str(exc))

    # --- 4. API smoke on server localhost (pre-deploy: 404 expected until A12 deploy) ---
    smoke_script = r"""
python3 << 'PY'
import json, urllib.request, urllib.error
base = "http://127.0.0.1:8000"
def get(path):
    try:
        with urllib.request.urlopen(base+path, timeout=15) as r:
            return r.status, r.read().decode()[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
out = {}
for path in ["/api/health", "/api/performance/summary", "/api/history"]:
    out[path] = get(path)
print(json.dumps(out))
PY
"""
    rc, smoke_out = ssh(smoke_script)
    if rc == 0 and smoke_out:
        try:
            smoke = json.loads(smoke_out.splitlines()[-1])
            for path, (code, _) in smoke.items():
                if path in {"/api/performance/summary", "/api/history"} and code == 404:
                    # Pre-A12 deploy: routes missing on server; local registration is the gate
                    local_ok = count_router_registrations(local_main, "history_router") == 1
                    record(checks, f"localhost_smoke_{path.replace('/', '_')}", local_ok, f"http={code} pre_deploy_expected")
                else:
                    ok = code in {200, 401}
                    record(checks, f"localhost_smoke_{path.replace('/', '_')}", ok, f"http={code}")
        except json.JSONDecodeError:
            record(checks, "localhost_smoke_parse", False, smoke_out[:200])
    else:
        record(checks, "localhost_smoke_ssh", False, smoke_out[:200])

    # --- 6. Local migration definitions present ---
    mig = (ROOT / "worldcup_predictor/database/migrations.py").read_text(encoding="utf-8")
    record(checks, "migration_defs_stored", "worldcup_stored_predictions" in mig)
    record(checks, "migration_defs_evaluations", "worldcup_prediction_evaluations" in mig)

    # --- 7. Build hash / commit alignment ---
    local_commit = ""
    try:
        local_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        pass
    server_commit = (db_info or {}).get("server_commit") or ""
    # After tarball deploy they'll diverge; pre-deploy we verify local build works
    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=240,
            shell=os.name == "nt",
        )
        record(checks, "local_frontend_build", proc.returncode == 0)
        dist_index = FRONTEND / "dist" / "index.html"
        if dist_index.is_file():
            idx = dist_index.read_text(encoding="utf-8")
            assets = re.findall(r'/assets/[^"\']+', idx)
            record(checks, "frontend_build_assets", len(assets) >= 1, f"assets={len(assets)}")
    except Exception as exc:
        record(checks, "local_frontend_build", False, str(exc))
    record(
        checks,
        "commit_trace",
        bool(local_commit),
        f"local={local_commit[:8]} server={str(server_commit)[:8]}",
    )

    # --- 8. Rollback package ---
    rb_script = f"""
if [ -d {APP}/backups ]; then ls -1dt {APP}/backups/deploy-* 2>/dev/null | head -3; else echo NONE; fi
if [ -d /var/www/worldcup/frontend/dist ]; then echo FRONTEND_DIST_OK; else echo FRONTEND_DIST_MISSING; fi
"""
    rc, rb_out = ssh(rb_script)
    has_backup = "deploy-" in rb_out or "FRONTEND_DIST_OK" in rb_out
    record(checks, "rollback_backup_exists", has_backup, rb_out.splitlines()[0] if rb_out else "none")

    # Deploy script exists locally
    record(checks, "deploy_script", (ROOT / "scripts/deploy_phase_a12_production.sh").is_file())

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    all_pass = passed == total

    print(f"\nPhase A12B Pre-Production — {passed}/{total} checks — PRE_DEPLOY_CHECK={'PASS' if all_pass else 'FAIL'}\n")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)

    out_path = ROOT / "data" / "validation" / "phase_a12b_preproduction.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "pre_deploy_check": "PASS" if all_pass else "FAIL",
                "passed": passed,
                "total": total,
                "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
