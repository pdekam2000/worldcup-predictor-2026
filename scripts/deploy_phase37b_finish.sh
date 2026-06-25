#!/usr/bin/env bash
set -euo pipefail
APP=/opt/worldcup-predictor
BACKUP=$(ls -dt "${APP}/backups/deploy-phase37b-"* 2>/dev/null | head -1)

set -a
source "${APP}/.env.production"
set +a

echo "=== enum check (psql) ==="
psql "${DATABASE_URL}" -t -c "SELECT unnest(enum_range(NULL::user_role))::text;" 2>&1 | tee "${BACKUP}/enum_check.log"

echo "=== 5. Restart ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || true

_run_validation() {
  sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
    "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python $1"
}

echo "=== 6. Env diagnostic ==="
_run_validation scripts/diagnose_env_providers.py 2>&1 | tee "${BACKUP}/diagnose_env.log"

echo "=== 7. Validations ==="
_run_validation scripts/validate_phase36c_env_wiring.py 2>&1 | tee "${BACKUP}/validate_phase36c.log" | tail -12
_run_validation scripts/validate_phase36b_placeholder_repair.py 2>&1 | tee "${BACKUP}/validate_phase36b.log" | tail -12
_run_validation scripts/validate_phase37a_admin_security.py 2>&1 | tee "${BACKUP}/validate_phase37a.log" | tail -15
_run_validation scripts/validate_phase34b_stale_confidence_cache_fix.py 2>&1 | tee "${BACKUP}/validate_phase34b.log" | tail -10
_run_validation scripts/validate_phase35_accuracy_driven_optimization.py 2>&1 | tee "${BACKUP}/validate_phase35.log" | tail -10

echo "=== 8. Before repair ==="
curl -sf "http://127.0.0.1:8000/api/predict/1489393" 2>/dev/null | tee "${BACKUP}/fixture1489393_before.json" | python3 -c "import sys,json; d=json.load(sys.stdin); print('confidence', d.get('confidence'), 'cache', d.get('cache_source'))" || echo "predict failed"

echo "=== 9. Repair ==="
_run_validation "scripts/repair_placeholder_predictions.py --fixture-id 1489393" 2>&1 | tee "${BACKUP}/repair_1489393.log" | tail -25

echo "=== 10. After repair ==="
curl -sf -X POST "http://127.0.0.1:8000/api/predict/1489393?force_refresh=true" 2>/dev/null | tee "${BACKUP}/fixture1489393_after_refresh.json" | python3 -c "import sys,json; d=json.load(sys.stdin); print('refresh confidence', d.get('confidence'), 'cache', d.get('cache_source'))" || true
curl -sf "http://127.0.0.1:8000/api/predict/1489393" 2>/dev/null | tee "${BACKUP}/fixture1489393_cached.json" | python3 -c "import sys,json; d=json.load(sys.stdin); print('cached confidence', d.get('confidence'), 'cache', d.get('cache_source'))" || true

echo "=== 11. Smoke ==="
curl -sf http://127.0.0.1:8000/api/health | tee "${BACKUP}/health.json"
echo ""
echo -n "admin_health_unauth: "
curl -sf -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/admin/health || echo "000"
echo -n "admin_gate_unauth: "
curl -sf -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/api/admin/gate/verify -H "Content-Type: application/json" -d '{"access_key":"x"}' || echo "000"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
