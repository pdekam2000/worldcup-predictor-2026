#!/usr/bin/env bash
# Pack Phase 63 enterprise deploy tarball
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/phase63_deploy.tar.gz}"
cd "${ROOT}"
tar czf "${OUT}" \
  worldcup_predictor/auth/rbac.py \
  worldcup_predictor/auth/user_management.py \
  worldcup_predictor/api/deps.py \
  worldcup_predictor/api/web_auth.py \
  worldcup_predictor/api/main.py \
  worldcup_predictor/api/routes/owner.py \
  worldcup_predictor/owner/__init__.py \
  worldcup_predictor/owner/platform_service.py \
  worldcup_predictor/database/postgres/enums.py \
  alembic/versions/014_enterprise_rbac.py \
  scripts/migrate_phase63_enterprise_roles.py \
  scripts/ensure_owner_account.py \
  scripts/validate_phase63_enterprise_platform.py \
  scripts/deploy_phase63_production.sh \
  scripts/deploy_phase63_smoke.sh \
  base44-d/src/lib/rbac.js \
  base44-d/src/lib/roles.js \
  base44-d/src/lib/navConfig.js \
  base44-d/src/lib/ownerNavConfig.js \
  base44-d/src/api/saasApi.js \
  base44-d/src/App.jsx \
  base44-d/src/components/OwnerRoute.jsx \
  base44-d/src/components/AdminRoute.jsx \
  base44-d/src/components/SuperAdminRoute.jsx \
  base44-d/src/components/owner/OwnerLayout.jsx \
  base44-d/src/pages/Login.jsx \
  base44-d/src/pages/OwnerLogin.jsx \
  base44-d/src/pages/owner/OwnerCommandCenter.jsx \
  base44-d/src/pages/owner/OwnerAutonomousPage.jsx \
  base44-d/src/pages/owner/OwnerMonitoringPage.jsx \
  base44-d/src/pages/owner/OwnerNotificationsPage.jsx \
  base44-d/src/pages/owner/OwnerPerformancePage.jsx \
  base44-d/src/pages/owner/OwnerHealthPage.jsx
echo "PACKED: ${OUT}"
