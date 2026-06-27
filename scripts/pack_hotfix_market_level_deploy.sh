#!/usr/bin/env bash
# Pack HOTFIX — market-level result evaluation + best bet winrate (run locally before scp)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/hotfix_market_level_deploy.tar.gz}"

cd "${ROOT}"
tar czf "${OUT}" \
  worldcup_predictor/api/market_level_evaluation.py \
  worldcup_predictor/automation/worldcup_background/pick_evaluator.py \
  worldcup_predictor/api/archive_evaluation_join.py \
  worldcup_predictor/api/evaluated_results.py \
  worldcup_predictor/api/global_prediction_archive.py \
  worldcup_predictor/api/routes/results.py \
  base44-d/src/lib/archiveFilters.js \
  base44-d/src/lib/archiveStatus.js \
  base44-d/src/components/archive/MarketBreakdownPanel.jsx \
  base44-d/src/components/archive/ArchiveCard.jsx \
  base44-d/src/pages/PredictionResultsPage.jsx \
  base44-d/src/pages/ArchivePage.jsx \
  base44-d/src/api/saasApi.js \
  scripts/validate_hotfix_market_level_result_evaluation.py \
  scripts/refresh_market_level_evaluations.py \
  scripts/deploy_hotfix_market_level_production.sh \
  scripts/deploy_hotfix_market_level_smoke.sh

echo "PACKED: ${OUT}"
ls -lh "${OUT}"
