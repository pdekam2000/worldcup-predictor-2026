#!/usr/bin/env bash
# Continue Gate-0 after checkout (migrations + restart + probes).
set -euo pipefail
APP=/opt/worldcup-predictor
cd "$APP"
PYTHON="$APP/.venv/bin/python"
API_BASE=http://127.0.0.1:8000
FI_DB="$APP/data/football_intelligence.db"
SERVICES="worldcup-api worldcup-gpt-actions"
RUN_DIR="$(ls -1dt "$APP"/backups/infra_deploy/* | head -n1)"
echo "RUN_DIR=$RUN_DIR"
echo "HEAD=$(git rev-parse HEAD)"

echo "=== apply migrations ==="
"$PYTHON" /tmp/apply_infra_migrations.py

echo "=== restart services ==="
systemctl restart $SERVICES
sleep 4
for svc in $SERVICES; do
  systemctl is-active --quiet "$svc" || { echo "FATAL inactive $svc"; exit 1; }
done
systemctl is-active --quiet nginx && echo nginx=active || echo WARN_nginx

echo "=== healthcheck ==="
"$PYTHON" deployment/post_deploy_healthcheck.py \
  --api-base "$API_BASE" --fi-db "$FI_DB" \
  --out "$RUN_DIR/post_deploy_healthcheck.json"

echo "=== canonical regression ==="
"$PYTHON" deployment/canonical_regression_probe.py \
  --mode after --baseline-dir "$RUN_DIR" --fi-db "$FI_DB" \
  --out-md "$RUN_DIR/canonical_regression_report.md" \
  --out-json "$RUN_DIR/canonical_regression.json"

echo "=== shadow probe ==="
"$PYTHON" deployment/shadow_probe.py \
  --fi-db "$FI_DB" \
  --out-md "$RUN_DIR/shadow_probe_report.md" \
  --out-json "$RUN_DIR/shadow_probe.json"

echo "=== journal secret scan ==="
for svc in $SERVICES; do
  journalctl -u "$svc" -n 80 --no-pager >"$RUN_DIR/journal_${svc}.log" || true
done
if grep -Eiq 'api[_-]?key|jwt_secret|password=|bearer [a-z0-9]{20,}' "$RUN_DIR"/journal_*.log 2>/dev/null; then
  echo "FATAL secrets in journal"; exit 1
fi
echo log_secret_scan=ok

PRE_COMMIT="$(tr -d '\r\n' <"$RUN_DIR/pre_commit.txt")"
POST_COMMIT="$(git rev-parse HEAD)"
cat >"$RUN_DIR/DEPLOYMENT_SUMMARY.txt" <<EOF
status=SUCCESS
pre_commit=$PRE_COMMIT
post_commit=$POST_COMMIT
validated_infra=537266d
package_tip=$POST_COMMIT
migrations=research_football_strength_lambda_v2.sql,research_alternate_totals_capture_status.sql
services_restarted=$SERVICES
backup_dir=$RUN_DIR
canonical_promotion=NONE
lambda_v2_canonical=NO
exact_v2_canonical=NO
EOF
cat "$RUN_DIR/DEPLOYMENT_SUMMARY.txt"
