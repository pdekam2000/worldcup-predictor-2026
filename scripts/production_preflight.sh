#!/usr/bin/env bash
# Phase 2 — production preflight (fail-closed). No secrets printed.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/deploy_hardening.sh
source "${SCRIPT_DIR}/lib/deploy_hardening.sh"

APP="${DEPLOY_APP:-/opt/worldcup-predictor}"
TARGET_SHA="${1:-}"
MANIFEST_DIR="${APP}/artifacts/deploy_manifests"
TS="$(date -u +%Y%m%d_%H%M%S)"

deploy_init "preflight" "${TARGET_SHA:-none}"

fail() {
  deploy_log "PREFLIGHT_FAIL: $*"
  deploy_finish_fail "preflight"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

if [[ ! -d "${APP}" ]]; then
  fail "application directory missing: ${APP}"
fi

if [[ ! -d "${APP}/.git" ]]; then
  fail "git repository missing under ${APP}"
fi

cd "${APP}"

CURRENT_SHA="$(git rev-parse HEAD)"
deploy_log "current_sha=${CURRENT_SHA}"

if [[ -z "${TARGET_SHA}" ]]; then
  fail "target SHA required as first argument"
fi

if ! git cat-file -e "${TARGET_SHA}^{commit}" 2>/dev/null; then
  fail "target SHA not found in local repository: ${TARGET_SHA}"
fi

if ! git merge-base --is-ancestor "${CURRENT_SHA}" "${TARGET_SHA}" 2>/dev/null; then
  fail "target SHA is not a fast-forward from current HEAD (ff-only required)"
fi

if [[ "${CURRENT_SHA}" == "${TARGET_SHA}" ]]; then
  deploy_log "already at target SHA — deploy is a no-op"
fi

git fetch origin main >/dev/null 2>&1 || fail "cannot fetch origin/main"

if ! git merge-base --is-ancestor "${TARGET_SHA}" "origin/main" 2>/dev/null; then
  fail "target SHA is not contained in origin/main history"
fi

# Dirty tree classification — refuse source drift; allow documented runtime paths only.
DIRTY_JSON="$(python3 - <<'PY'
import json, re, subprocess, sys

APP = sys.argv[1]
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

r = subprocess.run(
    ["git", "status", "--porcelain", "-uall"],
    capture_output=True,
    text=True,
    cwd=APP,
)
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
    "env_config": [e for e in entries if e["category"] == "env_config"],
}
print(json.dumps(out))
PY
"${APP}")"

SOURCE_DRIFT="$(echo "${DIRTY_JSON}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('source_code_drift',[])))")"
ENV_DRIFT="$(echo "${DIRTY_JSON}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('env_config',[])))")"

if [[ "${SOURCE_DRIFT}" -gt 0 ]]; then
  fail "uncommitted source code drift on production (${SOURCE_DRIFT} file(s))"
fi

if [[ "${ENV_DRIFT}" -gt 0 ]]; then
  fail "environment file drift detected — .env.production must not be modified during deploy"
fi

if [[ ! -f "${APP}/.env.production" ]]; then
  fail "required production environment file missing: ${APP}/.env.production"
fi

if [[ ! -x "${APP}/.venv/bin/python" ]]; then
  fail "production venv missing: ${APP}/.venv/bin/python"
fi

require_cmd git
require_cmd python3
require_cmd curl
require_cmd sha256sum

if ! systemctl list-unit-files worldcup-api.service >/dev/null 2>&1; then
  fail "systemd unit worldcup-api not found"
fi

if [[ ! -x "${APP}/scripts/backup_sqlite.sh" ]] && [[ ! -f "${APP}/data/football_intelligence.db" ]]; then
  deploy_log "WARN: backup_sqlite.sh missing and SQLite DB absent — backup gate may be limited"
fi

if [[ ! -x "${APP}/scripts/production_health_check.sh" ]]; then
  fail "health-check script missing: scripts/production_health_check.sh"
fi

mkdir -p "${MANIFEST_DIR}"
MANIFEST="${MANIFEST_DIR}/preflight_${TS}.json"
SERVICE_STATE="$(systemctl is-active worldcup-api 2>/dev/null || echo unknown)"

python3 - <<PY
import json
from pathlib import Path
payload = {
    "deployment_id": "${DEPLOY_SESSION_ID}",
    "timestamp_utc": "${TS}",
    "old_sha": "${CURRENT_SHA}",
    "target_sha": "${TARGET_SHA}",
    "service_state_before": "${SERVICE_STATE}",
    "dirty_classification": json.loads('''${DIRTY_JSON}'''),
    "app_path": "${APP}",
}
Path("${MANIFEST}").write_text(json.dumps(payload, indent=2), encoding="utf-8")
print("manifest=" + "${MANIFEST}")
PY

deploy_log "PREFLIGHT_OK current=${CURRENT_SHA} target=${TARGET_SHA}"
deploy_finish_ok
echo "PREFLIGHT_OK manifest=${MANIFEST}"
