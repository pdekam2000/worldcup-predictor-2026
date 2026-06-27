#!/usr/bin/env bash
# Pack HOTFIX H1+H2 deploy tarball (run locally before scp)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/hotfix_h1_h2_deploy.tar.gz}"

cd "${ROOT}"
tar czf "${OUT}" \
  worldcup_predictor/api/routes/predictions.py \
  worldcup_predictor/api/match_center_helpers.py \
  worldcup_predictor/api/display_helpers.py \
  base44-d/src/lib/imageResolver.js \
  base44-d/src/lib/predictionDetailProUtils.js \
  base44-d/src/api/worldcupApi.js \
  base44-d/src/components/ui/ErrorBoundary.jsx \
  base44-d/src/components/ui/SafeImage.jsx \
  base44-d/src/components/match/TeamBadge.jsx \
  base44-d/src/components/match-center/LeagueSelector.jsx \
  base44-d/src/components/match-center/EliteMatchCard.jsx \
  base44-d/src/components/match-center/PredictionExpandPanel.jsx \
  base44-d/src/pages/MatchDetailPage.jsx \
  scripts/validate_hotfix_h1_match_detail_logo_flags.py \
  scripts/deploy_hotfix_h1_h2_production.sh \
  scripts/deploy_hotfix_h1_h2_smoke.sh

echo "PACKED: ${OUT}"
ls -lh "${OUT}"
