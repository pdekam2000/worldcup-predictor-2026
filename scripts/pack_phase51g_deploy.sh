#!/usr/bin/env bash
# Build Phase 51G deploy tarball (run from repo root)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/phase51g_deploy.tar.gz}"

cd "${ROOT}"

tar czf "${OUT}" \
  worldcup_predictor/goal_timing/dashboard_service.py \
  worldcup_predictor/goal_timing/scheduler_state.py \
  worldcup_predictor/goal_timing/auto_evaluation_job.py \
  worldcup_predictor/goal_timing/prediction_service.py \
  worldcup_predictor/goal_timing/storage/repository.py \
  worldcup_predictor/api/routes/goal_timing.py \
  base44-d/src/api/saasApi.js \
  base44-d/src/pages/goalTiming/GoalTimingDashboardPage.jsx \
  base44-d/src/components/goalTiming/GoalTimingPageShell.jsx \
  scripts/validate_phase51g_egie_dashboard_polish.py \
  scripts/deploy_phase51g_production.sh \
  scripts/deploy_phase51g_smoke.sh

echo "Created ${OUT}"
ls -lh "${OUT}"
