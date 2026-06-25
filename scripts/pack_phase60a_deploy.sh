#!/usr/bin/env bash
# Pack Phase 60A full GUI + admin shadow deploy tarball (run locally before scp)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/phase60a_deploy.tar.gz}"

cd "${ROOT}"
tar czf "${OUT}" \
  worldcup_predictor/admin/elite_shadow_preview.py \
  worldcup_predictor/admin/elite_shadow_comparison.py \
  worldcup_predictor/admin/shadow_fixture_production_population.py \
  worldcup_predictor/admin/disagreement_quality_analysis.py \
  worldcup_predictor/api/deps.py \
  worldcup_predictor/api/main.py \
  worldcup_predictor/api/routes/admin_elite_shadow.py \
  worldcup_predictor/api/routes/admin_gate.py \
  worldcup_predictor/api/routes/admin_accuracy.py \
  worldcup_predictor/database/repository.py \
  worldcup_predictor/automation/worldcup_background/prediction_runner.py \
  base44-d/src/pages/EliteShadowPreview.jsx \
  base44-d/src/components/SuperAdminRoute.jsx \
  data/shadow/elite_orchestrator_predictions.jsonl \
  data/shadow/elite_orchestrator_evaluations.jsonl \
  data/shadow/root_cause_store/knowledge_records.jsonl \
  scripts/deploy_phase60a_production.sh \
  scripts/deploy_phase60a_smoke.sh \
  scripts/apply_phase60a_server_patch.py \
  scripts/validate_phase59b_owner_soft_launch.py \
  scripts/validate_phase59c_shadow_production_comparison.py \
  scripts/validate_phase60a_full_deploy.py \
  scripts/phase59d_populate_shadow_fixture_production_predictions.py \
  scripts/phase59e_disagreement_quality_analysis.py

echo "PACKED: ${OUT}"
ls -lh "${OUT}"
