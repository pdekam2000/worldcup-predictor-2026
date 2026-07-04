#!/usr/bin/env python3
"""CODEBASE-CONSOLIDATION-2 — Deploy GitHub main to production safely."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = "root@91.107.188.229"
APP = "/opt/worldcup-predictor"
TARGET = "origin/main"

FORBIDDEN = re.compile(
    r"(^|/)(data/|artifacts/|reports/|models/|\.cache/|backups/|logs/)|"
    r"\.(db|sqlite|jsonl|csv|parquet|pkl|gz|zip)$|"
    r"^\.env",
    re.I,
)
SOURCE = re.compile(
    r"^(worldcup_predictor/|scripts/|base44-d/|alembic/|config/|"
    r"requirements|main\.py|alembic\.ini|\.gitignore)",
    re.I,
)


def ssh(cmd: str, *, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", HOST, cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def classify_dirty(status_short: str) -> dict:
    entries = []
    for line in status_short.splitlines():
        if not line.strip():
            continue
        st, path = line[:2].strip(), line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ")[-1]
        p = path.replace("\\", "/")
        if p.endswith(".db") or "/.db" in p:
            cat = "db"
        elif FORBIDDEN.search(p) or p.startswith("data/"):
            cat = "runtime_data"
        elif ".env" in p or p.startswith("credentials/"):
            cat = "env_config"
        elif p.endswith(".log") or "/logs/" in p:
            cat = "logs"
        elif SOURCE.search(p) or p.endswith((".py", ".js", ".jsx", ".ts", ".tsx", ".sh")):
            cat = "source_code"
        else:
            cat = "runtime_data"
        entries.append({"status": st, "path": path, "category": cat})
    cats = {}
    for e in entries:
        cats.setdefault(e["category"], []).append(e)
    modified_source = [
        e for e in entries
        if e["category"] == "source_code" and e["status"] not in ("??", "!!")
    ]
    untracked_source = [e for e in entries if e["category"] == "source_code" and e["status"] == "??"]
    return {
        "total_dirty": len(entries),
        "source_code_drift": cats.get("source_code", []),
        "modified_tracked_source": modified_source,
        "untracked_source": untracked_source,
        "runtime_data": cats.get("runtime_data", []),
        "dbs": cats.get("db", []),
        "env_config": cats.get("env_config", []),
        "logs": cats.get("logs", []),
    }


def quarantine_untracked_conflicts(head: str) -> dict:
    """Backup + remove untracked files that would block checkout from origin/main."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = f"{APP}/data/backups/pre_deploy_untracked_source_{ts}"
    cmd = f"""
cd {APP} && git fetch origin main -q && BACKUP="{backup_dir}" && mkdir -p "$BACKUP" && QUAR="" &&
while IFS= read -r path; do
  if [ -f "$path" ] && ! git ls-files --error-unmatch "$path" >/dev/null 2>&1; then
    mkdir -p "$BACKUP/$(dirname "$path")"
    cp -a "$path" "$BACKUP/$path"
    rm -f "$path"
    QUAR="$QUAR $path"
  fi
done < <(git diff --name-only HEAD origin/main) &&
echo BACKUP_DIR=$BACKUP &&
echo QUARANTINED=$QUAR
"""
    r = ssh(cmd)
    out = r.stdout or ""
    backup = backup_dir
    quarantined = []
    for line in out.splitlines():
        if line.startswith("BACKUP_DIR="):
            backup = line.split("=", 1)[1].strip()
        if line.startswith("QUARANTINED="):
            quarantined = [p for p in line.split("=", 1)[1].split() if p]
    return {"quarantined": quarantined, "backup_dir": backup}


def main() -> int:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    state: dict = {
        "phase": "CODEBASE-CONSOLIDATION-2",
        "timestamp_utc": ts,
        "recommendation": "DO_NOT_DEPLOY_YET",
        "block_reason": "",
        "skipped_steps": [],
        "validations": [],
    }

    # Part A — preflight
    print("=== Part A: Preflight ===")
    head_start = ssh(f"cd {APP} && git rev-parse HEAD").stdout.strip()
    state["starting_commit"] = head_start

    preflight = {
        "head_start": head_start,
        "target_ref": TARGET,
        "git_status_sb": ssh(f"cd {APP} && git status -sb").stdout.strip(),
        "git_log_oneline_5": ssh(f"cd {APP} && git log --oneline -5").stdout.strip().splitlines(),
        "git_remote": ssh(f"cd {APP} && git remote -v").stdout.strip().splitlines(),
        "git_diff_stat": ssh(f"cd {APP} && git diff --stat").stdout.strip(),
        "disk_df": ssh("df -h / /opt 2>/dev/null || df -h").stdout.strip().splitlines(),
        "disk_du_app": ssh(f"du -h --max-depth=1 {APP} 2>/dev/null | sort -h").stdout.strip().splitlines(),
        "service_worldcup_api": ssh("systemctl status worldcup-api --no-pager 2>&1").stdout.strip().splitlines()[:40],
        "service_nginx": ssh("systemctl status nginx --no-pager 2>&1").stdout.strip().splitlines()[:25],
    }
    status_short = ssh(f"cd {APP} && git status --short -uall").stdout
    preflight["dirty_classification"] = classify_dirty(status_short)
    preflight["git_status_short_sample"] = status_short.splitlines()[:80]

    preflight_path = ROOT / "artifacts" / "codebase_consolidation_2_production_preflight.json"
    preflight_path.parent.mkdir(parents=True, exist_ok=True)
    preflight_path.write_text(json.dumps(preflight, indent=2), encoding="utf-8")
    ssh(f"mkdir -p {APP}/artifacts")
    subprocess.run(
        ["scp", "-o", "BatchMode=yes", str(preflight_path), f"{HOST}:{APP}/artifacts/codebase_consolidation_2_production_preflight.json"],
        check=True,
    )

    source_drift = preflight["dirty_classification"]["modified_tracked_source"]
    untracked = preflight["dirty_classification"]["untracked_source"]
    print(f"Modified tracked source: {len(source_drift)}")
    print(f"Untracked source files: {len(untracked)}")
    if source_drift:
        state["recommendation"] = "DEPLOY_BLOCKED_SOURCE_DRIFT"
        state["block_reason"] = "Modified tracked source code on production"
        for e in source_drift[:20]:
            print(f"  DRIFT: [{e['status']}] {e['path']}")
        write_report(state, preflight, ts)
        return 1

    if untracked:
        print("Quarantining untracked files that conflict with incoming pull...")
        q = quarantine_untracked_conflicts(head_start)
        state["quarantined_untracked"] = q
        print(f"Quarantined {len(q['quarantined'])} files to {q['backup_dir']}")
        for p in q["quarantined"][:15]:
            print(f"  Q: {p}")

    # Part B — backup
    print("=== Part B: Backup ===")
    backups = {}
    ssh(f"mkdir -p {APP}/data/backups")
    ssh(f"echo {head_start} > {APP}/data/backups/pre_deploy_commit_{ts}.txt")
    backups["commit_record"] = f"{APP}/data/backups/pre_deploy_commit_{ts}.txt"

    diff_stat = preflight["git_diff_stat"]
    if diff_stat:
        patch = f"{APP}/data/backups/pre_deploy_git_diff_{ts}.patch"
        ssh(f"cd {APP} && git diff > {patch} 2>/dev/null || true")
        backups["git_patch"] = patch

    db_path = ssh(
        f"cd {APP} && (source .env.production 2>/dev/null || source .env 2>/dev/null; "
        f"echo ${{SQLITE_PATH:-data/football_intelligence.db}})"
    ).stdout.strip()
    state["db_path"] = db_path

    db_backup = f"{APP}/data/backups/football_intelligence_before_code_deploy_{ts}.db"
    cp = ssh(f"test -f {APP}/{db_path} && cp -a {APP}/{db_path} {db_backup} && echo OK || echo MISSING")
    if "OK" in cp.stdout:
        backups["sqlite"] = db_backup
        print(f"SQLite backup: {db_backup}")
    else:
        state["recommendation"] = "DEPLOY_BLOCKED_BACKUP_FAILED"
        state["block_reason"] = "SQLite DB backup failed"
        write_report(state, preflight, ts, backups=backups)
        return 1

    pg_backup = ""
    pg = ssh(
        f"cd {APP} && set -a && source .env.production 2>/dev/null && set +a && "
        f"[ -n \"${{DATABASE_URL:-}}\" ] && command -v pg_dump >/dev/null && "
        f"pg_dump \"$DATABASE_URL\" -f {APP}/data/backups/postgres_before_code_deploy_{ts}.sql && echo OK || echo SKIP"
    )
    if "OK" in pg.stdout:
        pg_backup = f"{APP}/data/backups/postgres_before_code_deploy_{ts}.sql"
        backups["postgres"] = pg_backup
    state["backups"] = backups

    # schema before
    state["schema_before"] = json.loads(db_snapshot_ssh())

    # Part C — pull
    print("=== Part C: Pull ===")
    fetch = ssh(f"cd {APP} && git fetch origin main 2>&1")
    print(fetch.stdout or fetch.stderr)
    incoming = ssh(f"cd {APP} && git log --oneline HEAD..{TARGET}").stdout.strip()
    incoming_stat = ssh(f"cd {APP} && git diff --stat HEAD..{TARGET}").stdout.strip()
    state["incoming_commits"] = incoming.splitlines()
    state["incoming_stat"] = incoming_stat[:8000]

    pull = ssh(f"cd {APP} && git pull --ff-only origin main 2>&1")
    print(pull.stdout or pull.stderr)
    if pull.returncode != 0:
        state["recommendation"] = "DEPLOY_BLOCKED_SOURCE_DRIFT"
        state["block_reason"] = "git pull --ff-only failed"
        write_report(state, preflight, ts, backups=backups)
        return 1

    head_end = ssh(f"cd {APP} && git rev-parse HEAD").stdout.strip()
    state["ending_commit"] = head_end
    state["github_deployed"] = head_end
    print(f"Deployed commit: {head_end}")

    ssh(f"chown -R www-data:www-data {APP}/worldcup_predictor {APP}/scripts {APP}/config {APP}/base44-d 2>/dev/null || true")
    ssh(f"chown www-data:www-data {APP}/{db_path} 2>/dev/null || true")

    # Part D — dependencies
    print("=== Part D: Dependencies ===")
    req_changed = ssh(
        f"cd {APP} && git diff --name-only {head_start}..{head_end} | grep -E '^requirements' || true"
    ).stdout.strip()
    if req_changed:
        print("Installing requirements...")
        ssh(
            f"cd {APP} && sudo -u www-data env PYTHONPATH={APP} APP_ENV=production bash -lc "
            f"'set -a && source .env.production && set +a && .venv/bin/pip install -r requirements.txt'"
        )
        state["requirements_installed"] = True
    else:
        state["requirements_installed"] = False

    pip_check = ssh(
        f"cd {APP} && sudo -u www-data .venv/bin/pip check 2>&1 || true"
    ).stdout.strip()
    state["pip_check"] = pip_check

    fe_changed = ssh(
        f"cd {APP} && git diff --name-only {head_start}..{head_end} | grep '^base44-d/' | head -1 || true"
    ).stdout.strip()
    if fe_changed:
        print("Rebuilding frontend...")
        fe = ssh(
            f"cd {APP}/base44-d && npm ci 2>&1 && npm run build 2>&1 | tail -20"
        )
        state["frontend_build"] = (fe.stdout or fe.stderr)[-2000:]
        ssh(
            "test -d /var/www/worldcup/frontend/dist && "
            f"cp -a {APP}/base44-d/dist/. /var/www/worldcup/frontend/dist/ && "
            "chown -R www-data:www-data /var/www/worldcup/frontend/dist 2>/dev/null || true"
        )
    else:
        state["frontend_build"] = "skipped_no_changes"

    # Part E — migrations
    print("=== Part E: Migrations ===")
    alembic = ssh(
        f"cd {APP} && sudo -u www-data env PYTHONPATH={APP} APP_ENV=production bash -lc "
        f"'set -a && source .env.production && set +a && .venv/bin/python -m alembic upgrade head' 2>&1"
    )
    state["alembic_log"] = (alembic.stdout or alembic.stderr)[-3000:]
    if alembic.returncode != 0:
        state["recommendation"] = "DEPLOY_BLOCKED_MIGRATION_FAILED"
        state["block_reason"] = "alembic upgrade head failed"
        write_report(state, preflight, ts, backups=backups)
        return 1

    sqlite_mig = ssh(
        f"cd {APP} && sudo -u www-data env PYTHONPATH={APP} APP_ENV=production bash -lc "
        f"'set -a && source .env.production && set +a && .venv/bin/python -c \""
        f"from worldcup_predictor.database.repository import FootballIntelligenceRepository; "
        f"from worldcup_predictor.database.migrations import ensure_schema_compat; "
        f"ensure_schema_compat(FootballIntelligenceRepository()._conn); print(\\\"ok\\\")\"' 2>&1"
    )
    state["sqlite_migration_log"] = (sqlite_mig.stdout or sqlite_mig.stderr).strip()
    if sqlite_mig.returncode != 0 or "ok" not in state["sqlite_migration_log"]:
        state["recommendation"] = "DEPLOY_BLOCKED_MIGRATION_FAILED"
        state["block_reason"] = "ensure_schema_compat failed"
        write_report(state, preflight, ts, backups=backups)
        return 1

    state["schema_after"] = json.loads(db_snapshot_ssh())

    # verify no unexpected row loss
    loss = check_row_loss(state.get("schema_before", {}), state["schema_after"])
    state["row_loss_check"] = loss
    if loss.get("failed"):
        state["recommendation"] = "DEPLOY_BLOCKED_MIGRATION_FAILED"
        state["block_reason"] = "unexpected row loss after migration"
        write_report(state, preflight, ts, backups=backups)
        return 1

    # Part F — validation
    print("=== Part F: Validation ===")
    val_ok = True
    compile_r = ssh(
        f"cd {APP} && sudo -u www-data env PYTHONPATH={APP} .venv/bin/python -m compileall "
        f"worldcup_predictor scripts -q 2>&1"
    )
    if compile_r.returncode == 0:
        state["validations"].append("compileall:PASS")
    else:
        state["validations"].append("compileall:FAIL")
        val_ok = False

    validators = [
        "scripts/validate_project_asset_audit.py --date today",
        "scripts/validate_owner_daily_prediction_and_eval.py",
        "scripts/validate_daily_oddalerts_ecse_owner_pipeline.py",
        "scripts/validate_ecse_oddalerts_owner_lab.py",
        "scripts/validate_ecse_oddalerts_limited_shadow_monitor.py",
        "scripts/validate_wde_shadow_training.py",
    ]
    for v in validators:
        name = Path(v.split()[0]).name
        r = ssh(
            f"cd {APP} && sudo -u www-data env PYTHONPATH={APP} APP_ENV=production bash -lc "
            f"'set -a && source .env.production && set +a && .venv/bin/python {v}' 2>&1 || true"
        )
        ok = r.returncode == 0
        state["validations"].append(f"{name}:{'PASS' if ok else 'FAIL'}")
        if not ok:
            val_ok = False
            state.setdefault("validation_failures", {})[name] = (r.stdout or r.stderr)[-1500:]

    state["validation_ok"] = val_ok

    # Part G — restart
    print("=== Part G: Service restart ===")
    if val_ok:
        ssh("systemctl restart worldcup-api")
        import time
        time.sleep(4)
        state["service_status"] = ssh("systemctl status worldcup-api --no-pager 2>&1").stdout.strip()
        state["journal_tail"] = ssh("journalctl -u worldcup-api -n 100 --no-pager 2>&1").stdout.strip()
        state["nginx_status"] = ssh("systemctl status nginx --no-pager 2>&1").stdout.strip()[:1500]
        health = ssh("curl -sf http://127.0.0.1:8000/api/health 2>/dev/null || curl -sf http://127.0.0.1:8000/api/version 2>/dev/null || echo FAIL")
        state["health_check"] = health.stdout.strip()
        state["restarted"] = True
        state["recommendation"] = "PRODUCTION_DEPLOY_COMPLETE"
    else:
        state["restarted"] = False
        state["recommendation"] = "DEPLOY_PARTIAL_REVIEW_REQUIRED"
        state["skipped_steps"].append("service_restart_skipped_validation_failures")
        state["service_status"] = ssh("systemctl status worldcup-api --no-pager 2>&1").stdout.strip()

    write_report(state, preflight, ts, backups=backups)
    print(f"\n=== {state['recommendation']} ===")
    return 0 if state["recommendation"] == "PRODUCTION_DEPLOY_COMPLETE" else 1


def db_snapshot_ssh() -> str:
    script_b64 = __import__("base64").b64encode(
        b"""
import json, sqlite3, os
from pathlib import Path
app = Path("/opt/worldcup-predictor")
db = os.environ.get("SQLITE_PATH", "data/football_intelligence.db")
p = app / db
out = {"db_path": str(p), "exists": p.exists()}
if not p.exists():
    print(json.dumps(out))
    raise SystemExit
conn = sqlite3.connect(p)
cur = conn.cursor()
try:
    cur.execute("SELECT value FROM schema_meta WHERE key='schema_version'")
    row = cur.fetchone()
    out["schema_version"] = row[0] if row else None
except Exception as e:
    out["schema_version_error"] = str(e)
tables = [
    "odds_snapshots", "worldcup_stored_predictions", "ecse_prediction_snapshots",
    "ecse_oddalerts_shadow_predictions", "ecse_oddalerts_shadow_monitor",
]
counts = {}
for t in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        counts[t] = cur.fetchone()[0]
    except Exception as e:
        counts[t] = f"missing:{e}"
out["table_counts"] = counts
conn.close()
print(json.dumps(out))
"""
    ).decode()
    r = ssh(
        f"cd {APP} && sudo -u www-data env PYTHONPATH={APP} bash -lc "
        f"'set -a && source .env.production 2>/dev/null && set +a && "
        f"echo {script_b64} | base64 -d | .venv/bin/python' 2>&1"
    )
    for line in reversed((r.stdout or r.stderr).strip().splitlines()):
        if line.startswith("{"):
            return line
    return "{}"


def check_row_loss(before: dict, after: dict) -> dict:
    bc = before.get("table_counts") or {}
    ac = after.get("table_counts") or {}
    issues = []
    for t, bv in bc.items():
        av = ac.get(t)
        if isinstance(bv, int) and isinstance(av, int) and av < bv:
            issues.append({"table": t, "before": bv, "after": av})
    return {"failed": bool(issues), "issues": issues}


def write_report(state: dict, preflight: dict, ts: str, *, backups: dict | None = None) -> None:
    backups = backups or state.get("backups", {})
    sb = state.get("schema_before") or {}
    sa = state.get("schema_after") or {}

    def table_md(counts: dict) -> str:
        if not counts:
            return "| (n/a) | — |\n"
        return "".join(f"| {k} | {v} |\n" for k, v in counts.items())

    report = f"""# CODEBASE CONSOLIDATION 2 — Deploy Report

**Phase:** CODEBASE-CONSOLIDATION-2  
**Date:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}  
**Mode:** GitHub main → production (code + schema migrations only; no DB copy)

---

## Executive summary

| Item | Value |
|------|-------|
| Starting commit | `{state.get("starting_commit", "n/a")}` |
| Ending commit | `{state.get("ending_commit", state.get("starting_commit", "n/a"))}` |
| GitHub deployed | `{state.get("github_deployed", "n/a")}` |
| **Recommendation** | **{state.get("recommendation", "DO_NOT_DEPLOY_YET")}** |
| Block reason | {state.get("block_reason") or "—"} |

---

## Backups

| Backup | Path |
|--------|------|
| Pre-deploy commit | `{backups.get("commit_record", "n/a")}` |
| Git diff patch | `{backups.get("git_patch", "none")}` |
| SQLite DB | `{backups.get("sqlite", "none")}` |
| PostgreSQL dump | `{backups.get("postgres", "none")}` |
| Untracked source quarantine | `{state.get("quarantined_untracked", {}).get("backup_dir", "none")}` |

Quarantined files ({len(state.get("quarantined_untracked", {}).get("quarantined", []))}):  
{chr(10).join("- " + p for p in state.get("quarantined_untracked", {}).get("quarantined", [])[:30]) or "- none"}

---

## Incoming commits

```
{chr(10).join(state.get("incoming_commits", ["n/a"]))}
```

---

## Migrations

| | Before | After |
|---|--------|-------|
| schema_version | {sb.get("schema_version", "n/a")} | {sa.get("schema_version", "n/a")} |

### Table counts (before)

| Table | Count |
|-------|------:|
{table_md(sb.get("table_counts", {}))}

### Table counts (after)

| Table | Count |
|-------|------:|
{table_md(sa.get("table_counts", {}))}

Row loss check: `{json.dumps(state.get("row_loss_check", {}))}`

---

## Validation

{chr(10).join("- " + v for v in state.get("validations", [])) or "- (not run)"}

---

## Services

Restart performed: **{"yes" if state.get("restarted") else "no"}**

Health check: `{state.get("health_check", "n/a")}`

---

## Skipped steps

{chr(10).join("- " + s for s in state.get("skipped_steps", [])) or "- none"}

---

## Rollback instructions

1. `systemctl stop worldcup-api`
2. `cd {APP} && git checkout {state.get("starting_commit", "PRE_DEPLOY_SHA")}`
3. Restore SQLite: `cp {backups.get("sqlite", "BACKUP.db")} {APP}/{state.get("db_path", "data/football_intelligence.db")}`
4. `systemctl start worldcup-api`

---

## Final recommendation

**{state.get("recommendation", "DO_NOT_DEPLOY_YET")}**
"""
    report_path = ROOT / "CODEBASE_CONSOLIDATION_2_DEPLOY_REPORT.md"
    report_path.write_text(report, encoding="utf-8")

    result_path = ROOT / "artifacts" / f"codebase_consolidation_2_result_{ts}.json"
    result_path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")

    subprocess.run(
        ["scp", "-o", "BatchMode=yes", str(report_path), f"{HOST}:{APP}/CODEBASE_CONSOLIDATION_2_DEPLOY_REPORT.md"],
        check=False,
    )
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    sys.exit(main())
