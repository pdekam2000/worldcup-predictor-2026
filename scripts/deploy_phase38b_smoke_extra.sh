#!/usr/bin/env bash
# Phase 38B — additional production smoke checks
set -euo pipefail
APP=/opt/worldcup-predictor
BACKUP=/opt/worldcup-predictor/backups/deploy-phase38b-20260620-162610

echo "=== Predict market gating (unauth = free tier) ==="
curl -sf "http://127.0.0.1:8000/api/predict/1489393" 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
dm = d.get('detailed_markets') or {}
pm = d.get('plan_markets') or {}
print('plan_tier', pm.get('tier'))
print('has_match_winner', 'match_winner' in dm)
print('has_btts', 'btts' in dm)
print('has_ou', 'over_under_25' in dm)
print('has_first_goal', 'first_goal' in dm)
print('restricted', pm.get('restricted'))
" 2>&1 | tee "${BACKUP}/smoke_market_gating.log"

echo "=== Env keys (yes/no) ==="
grep -q '^ADMIN_CONTACT_EMAIL=' /opt/worldcup-predictor/.env.production && echo ADMIN_CONTACT_EMAIL=yes || echo ADMIN_CONTACT_EMAIL=no
grep -q '^SMTP_PORT=' /opt/worldcup-predictor/.env.production && echo SMTP_PORT=yes || echo SMTP_PORT=no
grep -q '^SMTP_HOST=' /opt/worldcup-predictor/.env.production && echo SMTP_HOST=yes || echo SMTP_HOST=no

echo "=== Validation summary lines ==="
grep 'validation:' "${BACKUP}/validate_phase38a.log" || true
grep 'validation:' "${BACKUP}/validate_phase37a.log" || true
grep 'validation:' "${BACKUP}/validate_phase36c.log" || true

echo "SMOKE_EXTRA_OK"
