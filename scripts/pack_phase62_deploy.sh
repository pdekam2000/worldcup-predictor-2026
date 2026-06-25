#!/usr/bin/env bash
# Pack Phase 62 deploy tarball (run locally before scp)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/phase62_deploy.tar.gz}"

cd "${ROOT}"
tar czf "${OUT}" \
  base44-d/src/index.css \
  base44-d/src/lib/navConfig.js \
  base44-d/src/components/dashboard/DashboardLayout.jsx \
  base44-d/src/components/layout/SidebarNav.jsx \
  base44-d/src/components/intelligence/index.jsx \
  base44-d/src/pages/OwnerLogin.jsx \
  base44-d/src/pages/ResearchHighlights.jsx \
  base44-d/src/pages/AdminPerformancePage.jsx \
  base44-d/src/pages/goalTiming/GoalTimingAccuracyPage.jsx \
  base44-d/src/pages/goalTiming/GoalTimingPerformancePage.jsx \
  scripts/ensure_owner_super_admin.py \
  scripts/apply_phase62_server_patch.py \
  scripts/validate_phase62_full_ui_rebrand.py \
  scripts/deploy_phase62_production.sh \
  scripts/deploy_phase62_smoke.sh

echo "PACKED: ${OUT}"
ls -lh "${OUT}"
