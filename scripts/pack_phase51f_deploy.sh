#!/usr/bin/env bash
# Build Phase 51F deploy tarball (run from repo root)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/phase51f_deploy.tar.gz}"

cd "${ROOT}"

tar czf "${OUT}" \
  worldcup_predictor/goal_timing/auto_evaluation_job.py \
  worldcup_predictor/goal_timing/evaluation_job.py \
  worldcup_predictor/goal_timing/result_refresh.py \
  worldcup_predictor/goal_timing/outcome_adapter.py \
  worldcup_predictor/goal_timing/learning_stats.py \
  worldcup_predictor/goal_timing/history_service.py \
  worldcup_predictor/goal_timing/evaluation.py \
  worldcup_predictor/goal_timing/storage/repository.py \
  worldcup_predictor/api/prediction_history_evaluation.py \
  worldcup_predictor/database/repository.py \
  worldcup_predictor/api/routes/goal_timing.py \
  worldcup_predictor/cli/commands.py \
  main.py \
  deployment/systemd/egie-goal-timing-evaluation.service \
  deployment/systemd/egie-goal-timing-evaluation.timer \
  scripts/install_phase51f_egie_eval_timer.sh \
  scripts/validate_phase51f_egie_auto_evaluation.py \
  scripts/validate_phase51e_goal_timing_evaluation.py \
  scripts/deploy_phase51f_production.sh \
  scripts/deploy_phase51f_smoke.sh \
  scripts/egie_phase51e_goal_timing_evaluation.py

echo "Created ${OUT}"
ls -lh "${OUT}"
