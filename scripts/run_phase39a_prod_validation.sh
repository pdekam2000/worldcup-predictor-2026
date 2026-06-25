#!/usr/bin/env bash
set -euo pipefail
APP=/opt/worldcup-predictor
runv() {
  sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
    "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python $1"
}
echo "=== 39A ==="
runv scripts/validate_phase39a_commercial_readiness.py | tail -30
echo "=== 38A ==="
runv scripts/validate_phase38a_subscription_system.py | tail -20
echo "=== 37A ==="
runv scripts/validate_phase37a_admin_security.py | tail -15
echo "=== Health ==="
curl -sf http://127.0.0.1:8000/api/health
echo
echo "=== Commercial API smoke ==="
curl -sf -o /dev/null -w "commercial_analytics_unauth: %{http_code}\n" http://127.0.0.1:8000/api/admin/commercial/analytics
curl -sf -o /dev/null -w "contact_admin_unauth: %{http_code}\n" -X POST http://127.0.0.1:8000/api/user/contact-admin -H "Content-Type: application/json" -d '{"subject":"x","message":"y","category":"support"}'
echo "=== Frontend smoke ==="
bash "${APP}/scripts/deploy_phase39a_smoke.sh" https://footballpredictor.it.com
