#!/usr/bin/env bash
set -euo pipefail
setfacl -m u:worldcup-gpt-actions:rw- /opt/worldcup-predictor/data/football_intelligence.db
UNIT=/etc/systemd/system/worldcup-gpt-actions.service
if ! grep -q '.env.production' "$UNIT"; then
  sed -i '/EnvironmentFile=\/etc\/worldcup-gpt-actions\/environment/i EnvironmentFile=/opt/worldcup-predictor/.env.production' "$UNIT"
fi
systemctl daemon-reload
systemctl restart worldcup-gpt-actions
sleep 2
systemctl is-active worldcup-gpt-actions
sudo -u worldcup-gpt-actions test -r /opt/worldcup-predictor/.env.production
sudo -u worldcup-gpt-actions test -w /opt/worldcup-predictor/data/football_intelligence.db
echo FIX_OK
