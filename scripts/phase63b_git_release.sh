#!/usr/bin/env bash
# Phase 63B — staged git release commits (run from repo root).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

exclude_from_index() {
  git reset -q HEAD -- "$@" 2>/dev/null || true
}

add_safe() {
  if [ -e "$1" ] || [ -d "$1" ]; then
    git add "$1"
  fi
}

echo "=== Excluding runtime / junk from index ==="
# Stage everything first pass will be selective per commit

commit_if_staged() {
  local msg="$1"
  if git diff --cached --quiet; then
    echo "SKIP (empty): $msg"
  else
    git commit -m "$msg"
    echo "COMMITTED: $msg"
    git log -1 --oneline
  fi
}

# --- Commit 1: Phases 28-59 foundation (backend-heavy) ---
git add alembic/versions/
git add deployment/
git add main.py requirements.txt
git add worldcup_predictor/
# peel phase 60-63 slices for later commits
exclude_from_index \
  worldcup_predictor/autonomous \
  worldcup_predictor/owner \
  worldcup_predictor/auth/rbac.py \
  worldcup_predictor/api/routes/owner.py \
  worldcup_predictor/api/routes/elite_world_cup.py \
  worldcup_predictor/api/routes/research_highlights.py \
  worldcup_predictor/research
git add scripts/
exclude_from_index \
  scripts/validate_phase60 \
  scripts/apply_phase60 \
  scripts/phase60 \
  scripts/validate_phase61 \
  scripts/apply_phase61 \
  scripts/validate_phase62 \
  scripts/apply_phase62 \
  scripts/validate_phase63 \
  scripts/apply_phase63 \
  scripts/deploy_phase63 \
  scripts/bump_owner \
  scripts/emergency_owner \
  scripts/emergency_login \
  scripts/ensure_owner \
  scripts/migrate_phase63 \
  scripts/reset_owner \
  scripts/phase63b_git_release.sh
# glob excludes
for f in scripts/*phase60* scripts/*phase61* scripts/*phase62* scripts/*phase63* scripts/emergency_* scripts/ensure_owner* scripts/reset_owner* scripts/bump_owner* scripts/migrate_phase63*; do
  [ -e "$f" ] && exclude_from_index "$f"
done
# Phase 28-59 reports and docs
git add PHASE_2*.md PHASE_3*.md PHASE_4*.md PHASE_5*.md HOTFIX_*.md 2>/dev/null || true
git add BILLING_*.md BUGFIX_*.md EGIE_*.md FEATURE_*.md HARMONIZATION_*.md PROVIDER_*.md STORAGE_*.md 2>/dev/null || true
git add PHASE_API_*.md PHASE_DL0_*.md PHASE_K2_*.md PHASE_ML1_*.md PHASE_OA*.md PRODUCTION_*.md ROOT_CAUSE_*.md SPORTMONKS_*.md 2>/dev/null || true
exclude_from_index PHASE_60*.md PHASE_61*.md PHASE_62*.md PHASE_63*.md EMERGENCY_*.md
commit_if_staged "feat(platform): Phases 28-59 backend, migrations, scripts, and reports"

# --- Commit 2: Phase 60 Research + Elite ---
git add PHASE_60*.md
git add worldcup_predictor/api/routes/elite_world_cup.py worldcup_predictor/api/routes/research_highlights.py worldcup_predictor/research/
git add base44-d/src/lib/apiError.js base44-d/src/pages/EliteWorldCupPage.jsx base44-d/src/pages/ResearchHighlights.jsx
for f in scripts/*phase60*; do [ -e "$f" ] && git add "$f"; done
# shared files touched in phase 60
git add worldcup_predictor/api/routes/goal_timing.py worldcup_predictor/goal_timing/storage/repository.py
git add base44-d/src/api/saasApi.js
commit_if_staged "feat(phase-60): research highlights, elite world cup, and request-failed fixes"

# --- Commit 3: Phase 61 Autonomous ---
git add PHASE_61*.md worldcup_predictor/autonomous/ worldcup_predictor/admin/autonomous_performance.py
git add worldcup_predictor/api/routes/admin_performance.py 2>/dev/null || true
for f in scripts/*phase61*; do [ -e "$f" ] && git add "$f"; done
commit_if_staged "feat(phase-61): autonomous prediction platform and admin performance API"

# --- Commit 4: Phase 62 UI Rebrand ---
git add PHASE_62*.md
git add base44-d/src/lib/navConfig.js base44-d/src/components/layout/ base44-d/src/components/terminal/
git add base44-d/src/pages/OwnerLogin.jsx base44-d/src/components/SuperAdminRoute.jsx
for f in scripts/*phase62* scripts/ensure_owner_super_admin.py; do [ -e "$f" ] && git add "$f"; done
git add base44-d/index.html base44-d/tailwind.config.js base44-d/src/index.css
commit_if_staged "feat(phase-62): terminal-dark UI rebrand, unified nav, and owner login route"

# --- Commit 5: Phase 63 Enterprise ---
git add PHASE_63_ENTERPRISE_PLATFORM_REPORT.md
git add worldcup_predictor/auth/rbac.py worldcup_predictor/owner/ worldcup_predictor/api/routes/owner.py
git add alembic/versions/014_enterprise_rbac.py
git add base44-d/src/lib/rbac.js base44-d/src/lib/roles.js base44-d/src/lib/ownerNavConfig.js
git add base44-d/src/components/OwnerRoute.jsx base44-d/src/components/owner/ base44-d/src/pages/owner/
git add base44-d/src/components/OwnerDashboardGate.jsx
for f in scripts/*phase63* scripts/ensure_owner_account.py scripts/migrate_phase63*; do
  [[ "$f" == *emergency* || "$f" == *phase63b* ]] && continue
  [ -e "$f" ] && git add "$f"
done
git add base44-d/src/App.jsx base44-d/src/api/authApi.js
commit_if_staged "feat(phase-63): enterprise RBAC, owner command center, and role migration"

# --- Commit 6: Phase 63 hotfixes + emergency ---
git add PHASE_63_PRODUCTION_VISIBILITY_HOTFIX_REPORT.md EMERGENCY_*.md
for f in scripts/bump_owner* scripts/emergency_* scripts/reset_owner* scripts/deploy_phase63_visibility* scripts/apply_phase63_visibility*; do
  [ -e "$f" ] && git add "$f"
done
git add base44-d/src/pages/Login.jsx worldcup_predictor/api/web_auth.py worldcup_predictor/auth/jwt_tokens.py
git add worldcup_predictor/api/routes/auth.py
commit_if_staged "fix(phase-63): production visibility, owner auth hotfixes, and password recovery"

# --- Commit 7: Remaining frontend + shared modifications ---
git add base44-d/
git add worldcup_predictor/
git add scripts/
git add data/validation/reports/ 2>/dev/null || true
exclude_from_index artifacts backups _pack_hotfix_weather _pack39b5 _pack_billing_hotfix _pack_phase41d _pack_phase42b _pack_phase42b_fix _pack_phase42c _pack_phase42d _pack_phase43 _active, dist_disable_verify dist_email_hotfix dist_hotfix
exclude_from_index data/shadow/*.jsonl data/validation/*.jsonl data/*.db data/football_intelligence.db
commit_if_staged "feat(frontend): accumulated SaaS UI, auth, and integration updates (Phases 28-63)"

# Final cleanup - ensure nothing critical left unstaged except exclusions
echo "=== Remaining status ==="
git status --short | head -40
