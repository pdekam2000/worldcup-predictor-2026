#!/usr/bin/env bash
# Pack Phase 59B deploy tarball (run locally before scp to server)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/phase59b_deploy.tar.gz}"

cd "${ROOT}"
tar czf "${OUT}" \
  worldcup_predictor/admin/elite_shadow_preview.py \
  worldcup_predictor/api/deps.py \
  worldcup_predictor/api/main.py \
  worldcup_predictor/api/routes/admin_elite_shadow.py \
  worldcup_predictor/api/routes/admin_gate.py \
  worldcup_predictor/api/routes/admin_accuracy.py \
  base44-d/src/pages/EliteShadowPreview.jsx \
  data/shadow/elite_orchestrator_predictions.jsonl \
  data/shadow/elite_orchestrator_evaluations.jsonl \
  data/shadow/root_cause_store/knowledge_records.jsonl \
  scripts/deploy_phase59b_production.sh \
  scripts/deploy_phase59b_smoke.sh \
  scripts/validate_phase59b_owner_soft_launch.py \
  scripts/apply_phase59b_server_patch.py

echo "PACKED: ${OUT}"
ls -lh "${OUT}"
