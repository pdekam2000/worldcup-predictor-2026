# PHASE 59B — Owner-Only Soft Launch Deploy (Elite Shadow Preview)

**Date:** 2026-06-25  
**Mode:** Deploy admin-only preview → Smoke test → Report  
**Status:** Deployed to production (owner-only)  
**Production host:** `91.107.188.229` / `footballpredictor.it.com`

### Final recommendation: **`OWNER_SOFT_LAUNCH_ACTIVE`**

---

## 1. Backup (pre-deploy)

| Item | Location |
|------|----------|
| Backup folder | `/opt/worldcup-predictor/backups/deploy-phase59b-20260625-034216` |
| Pre-deploy commit | `a6053cda09439b24cc7554f47f74cc85d849ec74` |
| SQLite DB | `football_intelligence.db` (copied into backup) |
| `.env.production` | copied into backup |
| Frontend dist | `frontend_dist/` snapshot in backup |
| Repo snapshot | `repo_snapshot_pre.tar.gz` |

---

## 2. What was deployed

### Backend
- `worldcup_predictor/admin/elite_shadow_preview.py` — safe JSONL loader
- `worldcup_predictor/api/routes/admin_elite_shadow.py` — **super_admin only** (`require_super_admin_user`)
- `worldcup_predictor/api/main.py` — registers elite-shadow + admin gate + admin accuracy routers
- `worldcup_predictor/api/deps.py` — includes `require_super_admin_user` (required on production)

### Shadow data (read-only)
- `data/shadow/elite_orchestrator_predictions.jsonl` (108 rows)
- `data/shadow/elite_orchestrator_evaluations.jsonl` (108 rows, all pending)
- `data/shadow/root_cause_store/knowledge_records.jsonl` (476 rows)

### Frontend (surgical patch)
- `base44-d/src/pages/EliteShadowPreview.jsx` (new)
- `App.jsx` — restored from git HEAD, patched with `/admin/elite-shadow` + `SuperAdminRoute`
- `navConfig.js` — Elite Shadow nav item **super_admin only**, hidden from regular admin nav
- `saasApi.js` — elite-shadow fetch helpers use **superAdminGate**

**Not changed:** public prediction routes, WDE, SaaS subscription logic, user-facing match/prediction pages.

---

## 3. Access control (owner-only)

| Layer | Control |
|-------|---------|
| API | `require_super_admin_user` on all `/api/admin/elite-shadow/*` |
| UI route | `SuperAdminRoute` wraps `/admin/elite-shadow` |
| Navigation | `roles: ["super_admin"]` + `showSuperAdminNav` gate |
| Public nav | Elite Shadow **not** in `DashboardLayout` public sections |

Regular `admin` role: **403** on API (super_admin gate).  
Unauthenticated: **401**.

---

## 4. Smoke test results (production)

| Check | Result |
|-------|--------|
| `GET /api/health` | **200** |
| `GET /api/admin/elite-shadow/summary` (no auth) | **401** |
| `GET /api/goal-timing/dashboard` (public) | **200** (unchanged) |
| Shadow JSONL readable by `www-data` | **PASS** |
| `GET /admin/elite-shadow` SPA shell | **200** |
| Elite Shadow UI marker in build | **PASS** |
| Elite-shadow only under `/api/admin/` | **PASS** |
| `validate_phase59b_owner_soft_launch.py` | **18/18 PASS** |

Script: `scripts/deploy_phase59b_smoke.sh` → **`SMOKE_ALL_PASS`**

---

## 5. Safety confirmations

| Requirement | Status |
|-------------|--------|
| Public users blocked from API | Yes (401/403) |
| Public route for elite-shadow API | No |
| `is_user_visible=false` on shadow payloads | Yes |
| Public prediction output unchanged | Yes (goal-timing dashboard 200) |
| WDE unchanged | Yes (no WDE files deployed) |
| SaaS plan logic unchanged | Yes |
| Elite Shadow not promoted to production picks | Yes (shadow JSONL only) |
| Token leakage in responses | No |

---

## 6. Owner access

**URL:** `https://footballpredictor.it.com/admin/elite-shadow`

Requirements:
1. Login as **super_admin** (owner)
2. Pass **super admin gate** (second factor)
3. Nav: Admin section → **Elite Shadow** (visible only to super_admin)

---

## 7. Deploy notes / incidents

1. **First deploy attempt:** full `App.jsx` replace broke frontend build (missing GoalTiming accuracy/performance pages on server). **Resolved** by restoring `App.jsx` from git HEAD and applying surgical patch (`scripts/apply_phase59b_server_patch.py`).
2. **API restart failure:** production `deps.py` lacked `require_super_admin_user`. **Resolved** by deploying updated `deps.py`.
3. **Service restored:** `worldcup-api` active, health **200**.

---

## 8. Decision questions

1. **Can owner inspect shadow predictions in production?** Yes — 18 fixtures, 108 prediction rows via admin API.
2. **Are public users blocked?** Yes — API auth + SuperAdminRoute + nav gating.
3. **Are evaluations visible?** Yes — 108 pending evaluation rows.
4. **Are root-cause records visible?** Yes — 476 records.
5. **Ready for owner-only soft launch?** **Yes**

### Final recommendation: **`OWNER_SOFT_LAUNCH_ACTIVE`**

---

## Constraints honored

- No public exposure of shadow predictions
- No WDE / live prediction / subscription changes
- Full backup before deploy
- No promotion of Elite Shadow to user-facing production output
