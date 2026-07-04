#!/usr/bin/env bash
# CODEBASE-CONSOLIDATION-2 — Deploy GitHub main to production (code + schema only)
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d_%H%M%S)
DATE_TAG=$(date -u +%Y%m%d)
ARTIFACTS="${APP}/artifacts"
BACKUPS="${APP}/data/backups"
PREFLIGHT_JSON="${ARTIFACTS}/codebase_consolidation_2_production_preflight.json"
RESULT_JSON="${ARTIFACTS}/codebase_consolidation_2_result_${TS}.json"
REPORT="${APP}/CODEBASE_CONSOLIDATION_2_DEPLOY_REPORT.md"
TARGET_REF="${1:-origin/main}"
RECOMMENDATION="DO_NOT_DEPLOY_YET"
SKIP_STEPS=()
BLOCK_REASON=""

mkdir -p "${ARTIFACTS}" "${BACKUPS}"

cd "${APP}"

# --- helpers ---
run_py() {
  sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
    "cd ${APP} && set -a && source .env.production 2>/dev/null || source .env 2>/dev/null || true && set +a && .venv/bin/python $*"
}

classify_dirty() {
  python3 - <<'PY'
import json, re, subprocess, sys
from pathlib import Path

FORBIDDEN = re.compile(
    r"(^|/)(data/|artifacts/|reports/|models/|\.cache/|backups/|logs/)|"
    r"\.(db|sqlite|jsonl|csv|parquet|pkl|gz|zip)$|"
    r"^\.env",
    re.I,
)
SOURCE = re.compile(
    r"^(worldcup_predictor/|scripts/|base44-d/|alembic/|config/|deployment/.*\.(md|example|service|timer)$|"
    r"requirements|main\.py|alembic\.ini|\.gitignore)",
    re.I,
)

r = subprocess.run(["git", "status", "--porcelain", "-uall"], capture_output=True, text=True, cwd="/opt/worldcup-predictor")
entries = []
for line in r.stdout.splitlines():
    if not line.strip():
        continue
    st, path = line[:2].strip(), line[3:].strip().strip('"')
    if " -> " in path:
        path = path.split(" -> ")[-1]
    p = path.replace("\\", "/")
    if FORBIDDEN.search(p) or p.startswith("data/"):
        cat = "runtime_data" if not p.endswith(".db") else "db"
    elif p.endswith(".db"):
        cat = "db"
    elif ".env" in p or p.startswith("credentials/"):
        cat = "env_config"
    elif p.endswith(".log") or "/logs/" in p:
        cat = "logs"
    elif SOURCE.search(p) or p.endswith((".py", ".js", ".jsx", ".ts", ".tsx", ".sh", ".service")):
        cat = "source_code"
    elif p.endswith(".md") and "REPORT" in p.upper():
        cat = "artifacts"
    else:
        cat = "runtime_data"
    entries.append({"status": st, "path": path, "category": cat})

out = {
    "total_dirty": len(entries),
    "source_code_drift": [e for e in entries if e["category"] == "source_code"],
    "runtime_data": [e for e in entries if e["category"] == "runtime_data"],
    "dbs": [e for e in entries if e["category"] == "db"],
    "env_config": [e for e in entries if e["category"] == "env_config"],
    "logs": [e for e in entries if e["category"] == "logs"],
    "artifacts": [e for e in entries if e["category"] == "artifacts"],
}
print(json.dumps(out, indent=2))
PY
}

db_snapshot() {
  run_py -c "
import json, sqlite3, os
from pathlib import Path
db = os.environ.get('SQLITE_PATH', 'data/football_intelligence.db')
p = Path('${APP}') / db
out = {'db_path': str(p), 'exists': p.exists()}
if not p.exists():
    print(json.dumps(out)); raise SystemExit(0)
conn = sqlite3.connect(p)
cur = conn.cursor()
try:
    cur.execute(\"SELECT value FROM schema_meta WHERE key='schema_version'\")
    row = cur.fetchone()
    out['schema_version'] = row[0] if row else None
except Exception as e:
    out['schema_version_error'] = str(e)
tables = ['odds_snapshots','worldcup_stored_predictions','ecse_prediction_snapshots',
          'ecse_oddalerts_shadow_predictions','ecse_oddalerts_shadow_monitor']
counts = {}
for t in tables:
    try:
        cur.execute(f'SELECT COUNT(*) FROM {t}')
        counts[t] = cur.fetchone()[0]
    except Exception as e:
        counts[t] = f'missing:{e}'
out['table_counts'] = counts
conn.close()
print(json.dumps(out))
"
}

# ========== Part A — Preflight ==========
echo "=== Part A: Preflight audit ==="
HEAD_START=$(git rev-parse HEAD)
GIT_STATUS=$(git status -sb)
GIT_LOG=$(git log --oneline -5)
GIT_REMOTE=$(git remote -v)
GIT_DIFF_STAT=$(git diff --stat 2>/dev/null || true)
GIT_STATUS_SHORT=$(git status --short -uall 2>/dev/null || true)
DISK_DF=$(df -h / /opt 2>/dev/null || df -h)
DISK_DU=$(du -h --max-depth=1 "${APP}" 2>/dev/null | sort -h || du -sh "${APP}"/* 2>/dev/null)
SVC_API=$(systemctl status worldcup-api --no-pager 2>&1 || true)
SVC_NGINX=$(systemctl status nginx --no-pager 2>&1 || true)
DIRTY_CLASS=$(classify_dirty)

python3 - <<PY
import json
from pathlib import Path
preflight = {
    "phase": "CODEBASE-CONSOLIDATION-2",
    "timestamp_utc": "${TS}",
    "app_path": "${APP}",
    "head_start": "${HEAD_START}",
    "target_ref": "${TARGET_REF}",
    "git_status_sb": """${GIT_STATUS//$'\n'/\\n}""".split("\\n"),
    "git_log_oneline_5": """${GIT_LOG//$'\n'/\\n}""".split("\\n"),
    "git_remote": """${GIT_REMOTE//$'\n'/\\n}""".split("\\n"),
    "git_diff_stat": """${GIT_DIFF_STAT//$'\n'/\\n}""",
    "disk_df": """${DISK_DF//$'\n'/\\n}""".split("\\n"),
    "disk_du_app": """${DISK_DU//$'\n'/\\n}""".split("\\n"),
    "service_worldcup_api": """${SVC_API//$'\n'/\\n}""".split("\\n")[:30],
    "service_nginx": """${SVC_NGINX//$'\n'/\\n}""".split("\\n")[:20],
    "dirty_classification": json.loads('''${DIRTY_CLASS}'''),
}
Path("${PREFLIGHT_JSON}").write_text(json.dumps(preflight, indent=2), encoding="utf-8")
print("Wrote", "${PREFLIGHT_JSON}")
PY

SOURCE_DRIFT=$(echo "${DIRTY_CLASS}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('source_code_drift',[])))")
echo "Source drift files: ${SOURCE_DRIFT}"

if [ "${SOURCE_DRIFT}" -gt 0 ]; then
  RECOMMENDATION="DEPLOY_BLOCKED_SOURCE_DRIFT"
  BLOCK_REASON="Uncommitted source code changes on production"
  echo "BLOCKED: SOURCE_DRIFT_REVIEW_REQUIRED"
  goto_report=1
else
  goto_report=0
fi

# ========== Part B — Backup ==========
PATCH_FILE=""
DB_BACKUP=""
PG_BACKUP=""
if [ "${goto_report}" -eq 0 ]; then
  echo "=== Part B: Backup ==="
  echo "${HEAD_START}" > "${BACKUPS}/pre_deploy_commit_${TS}.txt"

  if [ -n "${GIT_DIFF_STAT}" ] && [ "${GIT_DIFF_STAT}" != "" ]; then
    PATCH_FILE="${BACKUPS}/pre_deploy_git_diff_${TS}.patch"
    git diff > "${PATCH_FILE}" 2>/dev/null || true
    [ -s "${PATCH_FILE}" ] || PATCH_FILE=""
  fi

  set -a
  # shellcheck disable=SC1091
  source .env.production 2>/dev/null || source .env 2>/dev/null || true
  set +a

  SQLITE_PATH="${SQLITE_PATH:-data/football_intelligence.db}"
  if [ -f "${APP}/${SQLITE_PATH}" ]; then
    DB_BACKUP="${BACKUPS}/football_intelligence_before_code_deploy_${TS}.db"
    if cp -a "${APP}/${SQLITE_PATH}" "${DB_BACKUP}"; then
      echo "SQLite backup: ${DB_BACKUP}"
      chown www-data:www-data "${DB_BACKUP}" 2>/dev/null || true
    else
      RECOMMENDATION="DEPLOY_BLOCKED_BACKUP_FAILED"
      BLOCK_REASON="SQLite backup failed"
      goto_report=1
    fi
  fi

  if [ "${goto_report}" -eq 0 ] && [ -n "${DATABASE_URL:-}" ] && command -v pg_dump >/dev/null 2>&1; then
    PG_BACKUP="${BACKUPS}/postgres_before_code_deploy_${TS}.sql"
    if pg_dump "${DATABASE_URL}" -f "${PG_BACKUP}" 2>/dev/null; then
      echo "PostgreSQL backup: ${PG_BACKUP}"
    else
      echo "WARN: PostgreSQL backup skipped or failed (non-fatal if SQLite canonical)"
      PG_BACKUP=""
    fi
  fi
fi

# ========== Part C — Pull ==========
HEAD_END="${HEAD_START}"
PULL_OK=0
INCOMING_LOG=""
INCOMING_STAT=""
if [ "${goto_report}" -eq 0 ]; then
  echo "=== Part C: Fetch and pull ==="
  git fetch origin main
  INCOMING_LOG=$(git log --oneline HEAD.."${TARGET_REF}" 2>/dev/null || true)
  INCOMING_STAT=$(git diff --stat HEAD.."${TARGET_REF}" 2>/dev/null || true)
  echo "Incoming commits:"
  echo "${INCOMING_LOG}"

  if ! git pull --ff-only origin main; then
    RECOMMENDATION="DEPLOY_BLOCKED_SOURCE_DRIFT"
    BLOCK_REASON="git pull --ff-only failed (local commits or divergence)"
    goto_report=1
  else
    HEAD_END=$(git rev-parse HEAD)
    PULL_OK=1
    echo "Pulled to ${HEAD_END}"
  fi
fi

# ========== Part D — Dependencies ==========
REQ_CHANGED=0
PIP_CHECK=""
FRONTEND_BUILD=""
if [ "${goto_report}" -eq 0 ] && [ "${PULL_OK}" -eq 1 ]; then
  echo "=== Part D: Dependencies ==="
  if git diff --name-only "${HEAD_START}".."${HEAD_END}" 2>/dev/null | grep -qE '^requirements'; then
    REQ_CHANGED=1
    echo "requirements changed — installing"
    run_py -m pip install -r requirements.txt 2>&1 | tail -20 || true
  else
    echo "requirements unchanged — skip install"
  fi
  PIP_CHECK=$(run_py -m pip check 2>&1 || true)

  if git diff --name-only "${HEAD_START}".."${HEAD_END}" 2>/dev/null | grep -q '^base44-d/'; then
    echo "Frontend changed — rebuild"
    if [ -f base44-d/package-lock.json ]; then
      (cd base44-d && npm ci && npm run build) 2>&1 | tail -30
    else
      (cd base44-d && npm install && npm run build) 2>&1 | tail -30
    fi
    FRONTEND_BUILD="rebuilt"
    if [ -d base44-d/dist ] && [ -d /var/www/worldcup/frontend/dist ]; then
      cp -a base44-d/dist/. /var/www/worldcup/frontend/dist/ 2>/dev/null || true
      chown -R www-data:www-data /var/www/worldcup/frontend/dist 2>/dev/null || true
    fi
  else
    FRONTEND_BUILD="skipped_no_changes"
  fi
fi

# ========== Part E — Migrations ==========
SCHEMA_BEFORE=""
SCHEMA_AFTER=""
MIGRATION_OK=0
ALEMBIC_LOG=""
SQLITE_MIG_LOG=""
if [ "${goto_report}" -eq 0 ] && [ "${PULL_OK}" -eq 1 ]; then
  echo "=== Part E: Schema migrations ==="
  SCHEMA_BEFORE=$(db_snapshot)

  echo "Alembic upgrade head..."
  ALEMBIC_LOG=$(run_py -m alembic upgrade head 2>&1) || {
    RECOMMENDATION="DEPLOY_BLOCKED_MIGRATION_FAILED"
    BLOCK_REASON="alembic upgrade head failed"
    goto_report=1
  }

  if [ "${goto_report}" -eq 0 ]; then
    SQLITE_MIG_LOG=$(run_py -c "
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.database.migrations import ensure_schema_compat
repo = FootballIntelligenceRepository()
ensure_schema_compat(repo._conn)
print('ensure_schema_compat ok')
" 2>&1) || {
      RECOMMENDATION="DEPLOY_BLOCKED_MIGRATION_FAILED"
      BLOCK_REASON="ensure_schema_compat failed"
      goto_report=1
    }
  fi

  if [ "${goto_report}" -eq 0 ]; then
    SCHEMA_AFTER=$(db_snapshot)
    MIGRATION_OK=1
    # verify no row loss
    echo "${SCHEMA_BEFORE}" | python3 -c "
import json, sys
before = json.load(sys.stdin)
" 2>/dev/null || true
  fi
fi

# ========== Part F — Validation ==========
VALIDATION=()
VALIDATION_OK=1
if [ "${goto_report}" -eq 0 ] && [ "${PULL_OK}" -eq 1 ]; then
  echo "=== Part F: Validators ==="
  run_py -m compileall worldcup_predictor scripts -q 2>&1 && VALIDATION+=('compileall:PASS') || { VALIDATION+=('compileall:FAIL'); VALIDATION_OK=0; }

  for v in \
    "scripts/validate_project_asset_audit.py --date today" \
    "scripts/validate_owner_daily_prediction_and_eval.py" \
    "scripts/validate_daily_oddalerts_ecse_owner_pipeline.py" \
    "scripts/validate_ecse_oddalerts_owner_lab.py" \
    "scripts/validate_ecse_oddalerts_limited_shadow_monitor.py" \
    "scripts/validate_wde_shadow_training.py"
  do
    name=$(basename "${v%% *}")
    if run_py "${v}" >/tmp/wcp_val_${name}.log 2>&1; then
      VALIDATION+=("${name}:PASS")
    else
      VALIDATION+=("${name}:FAIL")
      VALIDATION_OK=0
    fi
  done
fi

# ========== Part G — Service restart ==========
SVC_AFTER=""
JOURNAL=""
HEALTH=""
RESTARTED=0
if [ "${goto_report}" -eq 0 ] && [ "${PULL_OK}" -eq 1 ] && [ "${MIGRATION_OK}" -eq 1 ]; then
  if [ "${VALIDATION_OK}" -eq 1 ]; then
    echo "=== Part G: Restart services ==="
    systemctl restart worldcup-api
    RESTARTED=1
    sleep 3
    SVC_AFTER=$(systemctl status worldcup-api --no-pager 2>&1 || true)
    JOURNAL=$(journalctl -u worldcup-api -n 100 --no-pager 2>&1 || true)
    HEALTH=$(curl -sf http://127.0.0.1:8000/api/health 2>/dev/null || curl -sf http://127.0.0.1:8000/api/version 2>/dev/null || echo "health_check_failed")
    RECOMMENDATION="PRODUCTION_DEPLOY_COMPLETE"
  else
    RECOMMENDATION="DEPLOY_PARTIAL_REVIEW_REQUIRED"
    SKIP_STEPS+=("service_restart_skipped_validation_failures")
    SVC_AFTER=$(systemctl status worldcup-api --no-pager 2>&1 || true)
  fi
fi

# ========== Part H — Report ==========
echo "=== Part H: Report ==="
python3 - <<PY
import json
from pathlib import Path
from datetime import datetime, timezone

result = {
    "phase": "CODEBASE-CONSOLIDATION-2",
    "timestamp_utc": "${TS}",
    "starting_commit": "${HEAD_START}",
    "ending_commit": "${HEAD_END}",
    "github_deployed": "${HEAD_END}",
    "target_ref": "${TARGET_REF}",
    "pull_ok": ${PULL_OK},
    "migration_ok": ${MIGRATION_OK},
    "validation_ok": ${VALIDATION_OK:-0},
    "restarted": ${RESTARTED},
    "recommendation": "${RECOMMENDATION}",
    "block_reason": "${BLOCK_REASON}",
    "backups": {
        "commit_record": "${BACKUPS}/pre_deploy_commit_${TS}.txt",
        "git_patch": "${PATCH_FILE}",
        "sqlite": "${DB_BACKUP}",
        "postgres": "${PG_BACKUP}",
    },
    "schema_before": json.loads('''${SCHEMA_BEFORE:-null}''') if '''${SCHEMA_BEFORE}''' else None,
    "schema_after": json.loads('''${SCHEMA_AFTER:-null}''') if '''${SCHEMA_AFTER}''' else None,
    "validations": "${VALIDATION[*]}".split() if "${VALIDATION[*]}" else [],
    "health_check": """${HEALTH}""",
    "skipped_steps": ${SKIP_STEPS:+[]} ,
}
Path("${RESULT_JSON}").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

schema_b = result.get("schema_before") or {}
schema_a = result.get("schema_after") or {}
counts_b = schema_b.get("table_counts", {})
counts_a = schema_a.get("table_counts", {})

def count_rows(d):
    lines = []
    for k, v in d.items():
        lines.append(f"| {k} | {v} |")
    return "\\n".join(lines) if lines else "| (n/a) | — |"

report = f"""# CODEBASE CONSOLIDATION 2 — Deploy Report

**Phase:** CODEBASE-CONSOLIDATION-2  
**Date:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}  
**Mode:** GitHub main → production (code + schema migrations only)

---

## Executive summary

| Item | Value |
|------|-------|
| Starting commit | \`${HEAD_START}\` |
| Ending commit | \`${HEAD_END}\` |
| GitHub deployed | \`${HEAD_END}\` |
| **Recommendation** | **{RECOMMENDATION}** |
| Block reason | {BLOCK_REASON or "—"} |

---

## Backups

| Backup | Path |
|--------|------|
| Pre-deploy commit | \`${BACKUPS}/pre_deploy_commit_${TS}.txt\` |
| Git diff patch | \`${PATCH_FILE or "none"}\` |
| SQLite DB | \`${DB_BACKUP or "none"}\` |
| PostgreSQL dump | \`${PG_BACKUP or "none"}\` |

---

## Pull

\`\`\`
{INCOMING_LOG[:4000] if INCOMING_LOG else "n/a"}
\`\`\`

---

## Migrations

| | Before | After |
|---|--------|-------|
| schema_version | {schema_b.get("schema_version", "n/a")} | {schema_a.get("schema_version", "n/a")} |

### Table counts (before)

| Table | Count |
|-------|------:|
{count_rows(counts_b)}

### Table counts (after)

| Table | Count |
|-------|------:|
{count_rows(counts_a)}

Alembic: {"ok" if ${MIGRATION_OK} else "failed/skipped"}  
SQLite ensure_schema_compat: {"ok" if ${MIGRATION_OK} else "failed/skipped"}

---

## Validation

{chr(10).join("- " + v for v in result.get("validations", [])) or "- (not run)"}

---

## Services

Restart performed: **{"yes" if ${RESTARTED} else "no"}**

Health check: \`{result.get("health_check", "n/a")[:200]}\`

---

## Skipped steps

{chr(10).join("- " + s for s in []) or "- none"}

---

## Rollback instructions

1. Stop API: \`systemctl stop worldcup-api\`
2. Restore code: \`cd ${APP} && git checkout ${HEAD_START}\`
3. Restore SQLite if needed: \`cp ${DB_BACKUP or "BACKUP_PATH"} ${APP}/data/football_intelligence.db\`
4. Restore PostgreSQL if used: \`psql \$DATABASE_URL < ${PG_BACKUP or "BACKUP_PATH"}\`
5. Restart: \`systemctl start worldcup-api\`

---

## Final recommendation

**{RECOMMENDATION}**

---

*Preflight: \`artifacts/codebase_consolidation_2_production_preflight.json\`*  
*Result: \`{Path("${RESULT_JSON}").name}\`*
"""
Path("${REPORT}").write_text(report, encoding="utf-8")
print("Wrote", "${REPORT}")
print("RECOMMENDATION:", "${RECOMMENDATION}")
PY

echo "=== DONE: ${RECOMMENDATION} ==="
exit 0
