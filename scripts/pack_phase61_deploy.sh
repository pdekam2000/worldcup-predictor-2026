#!/usr/bin/env bash
# Pack Phase 61 backend deploy tarball
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/phase61_deploy.tar.gz}"
cd "${ROOT}"
tar czf "${OUT}" \
  worldcup_predictor/autonomous \
  worldcup_predictor/admin/autonomous_performance.py \
  worldcup_predictor/api/routes/admin_performance.py \
  worldcup_predictor/api/main.py \
  worldcup_predictor/config/settings.py \
  worldcup_predictor/database/migrations.py \
  worldcup_predictor/cli/commands.py \
  main.py \
  deployment/systemd/worldcup-autonomous.service \
  deployment/systemd/worldcup-autonomous.timer \
  scripts/validate_phase61_autonomous_platform.py
echo "PACKED: ${OUT}"
