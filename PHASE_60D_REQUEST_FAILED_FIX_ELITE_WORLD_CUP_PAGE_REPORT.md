# Phase 60D — Request Failed Fix + Elite World Cup Page Report

**Date:** 2026-06-25  
**Scope:** Diagnose/fix “Request failed” pages, add Elite World Cup predictions (super_admin-only), validate, deploy, report.  
**Production:** https://footballpredictor.it.com (`91.107.188.229`)

---

## Executive Summary

| Item | Status |
|------|--------|
| Request failed root cause (goal timing) | **Fixed** — Postgres read failures degrade gracefully (HTTP 200 + empty data) |
| API error UX (401/403/404/500) | **Improved** — `apiError.js` + `saasApi` message mapping |
| Elite World Cup page `/elite/world-cup` | **Live** (super_admin-only) |
| API `GET /api/elite/world-cup/predictions` | **Live** — unauth → 401 |
| `ELITE_WC_PUBLIC_ENABLED` | **false** (default) |
| WDE / production engine / SaaS plans | **Unchanged** |
| Shadow promoted to production | **No** |
| Local validation | **28/28 PASS** |
| Production validation | **28/28 PASS** |
| Deploy | **Completed** (with surgical patches + manual API router recovery) |

### Final Recommendation

**`ADMIN_ONLY_READY`** + **`ELITE_WC_PAGE_ACTIVE`**

Elite World Cup is active for super_admin only. Request-failed issues on goal-timing dashboard are fixed at the API layer. Public exposure remains blocked until `ELITE_WC_PUBLIC_ENABLED=true` after further validation.

---

## Part A — “Request Failed” Diagnosis

### Root cause (primary)

**Goal timing dashboard** (`/goal-timing/dashboard`, `/goal-timing/*`) called `GET /api/goal-timing/dashboard`, which reads PostgreSQL via `GoalTimingRepository`. When Postgres was unreachable or slow (connection timeout), unhandled `SQLAlchemyError` bubbled up as **HTTP 500**. The frontend `saasApi` surfaced this as generic **“Request failed (500)”**.

### Pages tested / expected behavior

| Route | Auth | Failed endpoint (before) | HTTP (before) | Root cause | Fix |
|-------|------|--------------------------|---------------|------------|-----|
| `/goal-timing/dashboard` | Mixed | `/api/goal-timing/dashboard` | 500 | PG timeout in `list_predictions`, `list_evaluations_joined`, etc. | `_postgres_read_safe()` wrappers in repository |
| `/goal-timing/history` | Mixed | `/api/goal-timing/history` | 500 | Same PG read path | Same |
| `/goal-timing/accuracy` | Mixed | `/api/goal-timing/accuracy` | 500 | Same | Same |
| `/dashboard`, `/matches`, `/prediction` | User | Various user APIs | 401 when logged out | Expected — not a bug | `extractApiErrorMessage` → “Login required…” |
| `/admin/elite-shadow` | super_admin | `/api/admin/elite-shadow/*` | 401 unauth | Expected | Unchanged (401 correct) |
| `/elite/world-cup` | super_admin | `/api/elite/world-cup/predictions` | 401 unauth | Expected (new) | New gated endpoint |
| `/research/highlights` | Public | `/api/research/highlights` | 404 on prod initially | Route not deployed | Deployed in follow-up patch |
| `/account/settings` | User | N/A | 404 route | Legacy path | Redirect → `/settings` |
| `/analytics/accuracy` | User | N/A | 404 route | Legacy path | Redirect → `/accuracy` |
| `/admin/accuracy`, `/admin/learning` (nav) | admin | N/A | 404 SPA | No `App.jsx` route | **Not in scope** — nav legacy; no API “Request failed” |

### UI error handling improvements

| Status | User message |
|--------|----------------|
| 401 | Login required. Please sign in to continue. |
| 403 | Permission required. You do not have access to this resource. |
| 404 | Data not available yet. |
| 500+ | Server error. Please try again shortly. |
| Empty data | Empty state (dashboard returns 200 with zero counts when PG unavailable) |

**Files:** `base44-d/src/lib/apiError.js`, `base44-d/src/api/saasApi.js`

---

## Part B — Elite World Cup Page

### Route

- **Path:** `/elite/world-cup`
- **Title:** Elite World Cup Predictions
- **Guard:** `SuperAdminRoute` (frontend) + `require_super_admin_user` (API when `ELITE_WC_PUBLIC_ENABLED=false`)

### Page sections

1. **Elite World Cup Fixtures** — teams, date, market, elite pick, tier, pending/evaluated, **Experimental** badge  
2. **Elite Markets** — 1X2, first goal team, team to score first, goal timing (when present in shadow data)  
3. **Comparison with Production** — super_admin only: same/different pick, production vs elite confidence  
4. **Risk notice** — “Research statistics and experimental predictions. Not betting advice.”

### Labeling

All records include:

```json
{
  "is_elite": true,
  "is_experimental": true,
  "label": "Elite Experimental / Shadow-based research output"
}
```

`root_cause`, `component_contributions`, tokens, and internal paths are **stripped** before API response.

---

## Part C — Backend API

### Endpoint

`GET /api/elite/world-cup/predictions`

| Param | Description |
|-------|-------------|
| `market` | `all` \| `1x2` \| `first_goal_team` \| … |
| `tier` | `all` \| `A` \| `B` \| … |
| `status` | `all` \| `pending` \| `evaluated` |
| `limit` / `offset` | Pagination |

### Access

| `ELITE_WC_PUBLIC_ENABLED` | Behavior |
|---------------------------|----------|
| `false` (default) | super_admin + gate token; includes comparison summary |
| `true` (future) | Public/pro safe summary; no comparison internals |

### Data source

`data/shadow/elite_orchestrator_predictions.jsonl` — filtered to `world_cup_2026` / `world_cup` (108 shadow rows → 18 WC fixture bundles exposed).

### Example response (truncated, super_admin)

```json
{
  "access_mode": "super_admin",
  "total": 18,
  "label": "Elite Experimental / Shadow-based research output",
  "disclaimer": "Research statistics and experimental predictions. Not betting advice.",
  "fixtures": [
    {
      "fixture_id": 1489409,
      "fixture": {
        "home_team": "Curaçao",
        "away_team": "Ivory Coast",
        "kickoff_utc": "2026-06-25T20:00:00",
        "competition_key": "world_cup_2026"
      },
      "elite_pick": { "home": 0.049, "draw": 0.1155, "away": 0.8355 },
      "confidence_tier": "A",
      "status": "pending",
      "is_elite": true,
      "is_experimental": true,
      "label": "Elite Experimental / Shadow-based research output",
      "markets": [
        { "market_id": "1x2", "tier": "A", "status": "pending" },
        { "market_id": "first_goal_team", "prediction": "away", "tier": "A" }
      ]
    }
  ],
  "comparison_summary": { "available": true, "rows": [] }
}
```

---

## Part D — Navigation

- **Elite World Cup** added to `navConfig.js` and `DashboardLayout` admin items — **super_admin only**
- **Elite Shadow** remains super_admin only (unchanged)
- Normal users do **not** see admin elite nav items

---

## Part E — Validation

**Script:** `scripts/validate_phase60d_request_failed_and_elite_wc_page.py`

| Environment | Result |
|-------------|--------|
| Local | **28/28 PASS** |
| Production | **28/28 PASS** |

Key checks: health 200, goal-timing dashboard not 500, elite WC unauth blocked, no `root_cause` in public payloads, WDE/scoring engine unchanged, elite shadow unauth 401.

---

## Part F — Deploy

### Backups (production)

| Artifact | Path |
|----------|------|
| Deploy backup | `/opt/worldcup-predictor/backups/deploy-phase60d-20260625-064321` |
| Pre-deploy commit | `a6053cda09439b24cc7554f47f74cc85d849ec74` |
| DB snapshot | `football_intelligence.db`, `postgres_pre.sql` |
| Frontend dist | `frontend_dist/` |
| Env | `env.production` |
| Repo snapshot | `repo_snapshot_pre.tar.gz` |

### Deploy artifacts

- `scripts/pack_phase60d_deploy.sh`
- `scripts/deploy_phase60d_production.sh`
- `scripts/deploy_phase60d_smoke.sh`
- `scripts/apply_phase60a_server_patch.py` (preserves elite shadow GUI)
- `scripts/apply_phase60d_server_patch.py` (surgical App/nav/main/dashboard/saas patches)

### Post-deploy smoke (production)

| Check | Result |
|-------|--------|
| Homepage | 200 |
| `/elite/world-cup` SPA | 200 |
| `/admin/elite-shadow` SPA | 200 |
| `/api/health` | 200 |
| `/api/goal-timing/dashboard` | 200 |
| `/api/research/highlights` | 200 |
| `/api/elite/world-cup/predictions` (unauth) | 401 |
| `/api/admin/elite-shadow/summary` (unauth) | 401 |

### Deploy notes

- Frontend build deployed successfully; initial API restart failed due to full `main.py` overwrite referencing undeployed `research_highlights`. Recovered via surgical router patches.
- Production uses **surgical patches** rather than full `App.jsx` / `main.py` replace to preserve Phase 60A elite-shadow server state.

---

## Part G — Files Changed

### Backend

| File | Change |
|------|--------|
| `worldcup_predictor/goal_timing/storage/repository.py` | `_postgres_read_safe()` for PG reads including `list_predictions`, `get_prediction_by_fixture` |
| `worldcup_predictor/goal_timing/dashboard_service.py` | `postgres_available` hint in dashboard payload |
| `worldcup_predictor/config/settings.py` | `elite_wc_public_enabled` / `ELITE_WC_PUBLIC_ENABLED` |
| `worldcup_predictor/admin/elite_world_cup_predictions.py` | **New** — safe WC shadow aggregation |
| `worldcup_predictor/api/routes/elite_world_cup.py` | **New** — gated API route |
| `worldcup_predictor/api/main.py` | Elite WC + research highlights router registration (local; production patched surgically) |
| `worldcup_predictor/api/routes/research_highlights.py` | Deployed to production |
| `worldcup_predictor/research/highlights_service.py` | Deployed to production |

### Frontend

| File | Change |
|------|--------|
| `base44-d/src/lib/apiError.js` | **New** — error classification |
| `base44-d/src/api/saasApi.js` | `extractApiErrorMessage`, `fetchEliteWorldCupPredictions` |
| `base44-d/src/pages/EliteWorldCupPage.jsx` | **New** — Elite WC UI |
| `base44-d/src/App.jsx` | Route `/elite/world-cup`, redirects, `SuperAdminRoute` |
| `base44-d/src/lib/navConfig.js` | Elite WC nav, settings path fix |
| `base44-d/src/components/dashboard/DashboardLayout.jsx` | Admin elite nav (local; production patched) |

### Scripts

| File | Change |
|------|--------|
| `scripts/validate_phase60d_request_failed_and_elite_wc_page.py` | **New** |
| `scripts/pack_phase60d_deploy.sh` | **New** |
| `scripts/deploy_phase60d_production.sh` | **New** |
| `scripts/deploy_phase60d_smoke.sh` | **New** |
| `scripts/apply_phase60d_server_patch.py` | **New** |

### Unchanged (verified)

- `worldcup_predictor/decision/weighted_decision_engine.py`
- `worldcup_predictor/prediction/scoring_engine.py`
- SaaS plan configuration
- Production prediction engine (shadow not promoted)

---

## Rollback Plan

1. **API:** `tar xzf /opt/worldcup-predictor/backups/deploy-phase60d-20260625-064321/repo_snapshot_pre.tar.gz -C /opt/worldcup-predictor && systemctl restart worldcup-api`
2. **Frontend:** `rsync -a /opt/worldcup-predictor/backups/deploy-phase60d-20260625-064321/frontend_dist/ /var/www/worldcup/frontend/dist/`
3. **DB:** Restore `football_intelligence.db` / `postgres_pre.sql` only if data migration occurred (none in this phase)
4. **Env:** `cp backups/.../env.production .env.production` if needed
5. Verify: `/api/health`, homepage, `/admin/elite-shadow`, production predictions unchanged

---

## Next Steps (optional, not executed)

1. Set `ELITE_WC_PUBLIC_ENABLED=true` only after extended live validation
2. Wire `/admin/accuracy` nav routes or remove stale admin nav entries
3. Add `GoalTimingDashboardPage` error UX patch on production when terminal components are fully deployed

---

**STOP — Phase 60D complete.**
