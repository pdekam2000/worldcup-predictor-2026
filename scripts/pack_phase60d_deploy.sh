#!/usr/bin/env bash
# Pack Phase 60D deploy tarball (run locally before scp)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/phase60d_deploy.tar.gz}"

cd "${ROOT}"
tar czf "${OUT}" \
  worldcup_predictor/config/settings.py \
  worldcup_predictor/admin/elite_world_cup_predictions.py \
  worldcup_predictor/api/routes/elite_world_cup.py \
  worldcup_predictor/api/routes/research_highlights.py \
  worldcup_predictor/research/highlights_service.py \
  artifacts/phase60c_goal_event_backfill/research_highlights_cache.json \
  worldcup_predictor/goal_timing/storage/repository.py \
  worldcup_predictor/goal_timing/dashboard_service.py \
  base44-d/src/lib/apiError.js \
  base44-d/src/api/saasApi.js \
  base44-d/src/pages/EliteWorldCupPage.jsx \
  data/shadow/elite_orchestrator_predictions.jsonl \
  scripts/deploy_phase60d_production.sh \
  scripts/deploy_phase60d_smoke.sh \
  scripts/apply_phase60a_server_patch.py \
  scripts/apply_phase60d_server_patch.py \
  scripts/validate_phase60d_request_failed_and_elite_wc_page.py

echo "PACKED: ${OUT}"
ls -lh "${OUT}"
