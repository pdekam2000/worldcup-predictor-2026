#!/usr/bin/env bash
BACKUP=/opt/worldcup-predictor/backups/deploy-phase37b-20260620-160831
echo "=== BACKUP CONTENTS ==="
ls -la "$BACKUP"
echo "=== BEFORE FIXTURE ==="
wc -c "$BACKUP/fixture1489393_before.json" 2>/dev/null || true
head -c 400 "$BACKUP/fixture1489393_before.json" 2>/dev/null; echo
echo "=== CACHED FIXTURE ==="
python3 <<'PY'
import json
d=json.load(open("/opt/worldcup-predictor/backups/deploy-phase37b-20260620-160831/fixture1489393_cached.json"))
print("confidence", d.get("confidence"))
print("cache_source", d.get("cache_source"))
print("prediction", d.get("prediction"))
PY
echo "=== VALIDATION COUNTS ==="
grep -c PASS "$BACKUP/validate_phase36c.log" || true
grep -c PASS "$BACKUP/validate_phase36b.log" || true
grep -c PASS "$BACKUP/validate_phase37a.log" || true
grep -c PASS "$BACKUP/validate_phase34b.log" || true
grep -c PASS "$BACKUP/validate_phase35.log" || true
echo "=== ADMIN KEYS STATUS ==="
grep -q '^ADMIN_ACCESS_KEY=' /opt/worldcup-predictor/.env.production && echo ADMIN_ACCESS_KEY=configured
grep -q '^SUPER_ADMIN_ACCESS_KEY=' /opt/worldcup-predictor/.env.production && echo SUPER_ADMIN_ACCESS_KEY=configured
grep '^APP_ENV=' /opt/worldcup-predictor/.env.production | cut -d= -f1
echo "=== SERVICES ==="
systemctl is-active worldcup-api nginx
