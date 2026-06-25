# Phase 37B — Production Deploy Report (36C + 36B + 37A)

**Date:** 2026-06-20  
**Server:** 91.107.188.229  
**App path:** `/opt/worldcup-predictor`  
**Frontend path:** `/var/www/worldcup/frontend/dist`  
**Status:** **DEPLOY OK**

---

## Executive Summary

Phases **36C** (env wiring), **36B** (placeholder repair), and **37A** (admin security) were deployed to production in order. Backups were taken before changes. Alembic migration added `super_admin` to PostgreSQL `user_role`. Admin access keys were configured (generated on first deploy — values not logged). Fixture **1489393** was repaired from a provider-env placeholder row to a live prediction at **49.0%** confidence (`is_placeholder=false`). All five validation suites passed on production.

**Not deployed:** Sportmonks/xG promotion, Goal Minute phase (per scope).

---

## 1. Backup Paths

| Asset | Backup location |
|-------|-----------------|
| **Deploy bundle** | `/opt/worldcup-predictor/backups/deploy-phase37b-20260620-160831/` |
| SQLite DB | `.../football_intelligence.db` (272 MB) |
| PostgreSQL | `.../postgres.dump` |
| Frontend dist (pre-deploy) | `.../frontend_dist/` |
| Repo snapshot (pre-deploy) | `.../repo_snapshot_pre.tar.gz` |
| systemd unit | `.../worldcup-api.service` |
| `.env.production` path only | `.../env_production_path.txt` → `/opt/worldcup-predictor/.env.production` |
| Pre-deploy git commit | `267812e6e1c71258b78373161ade915c00b3ed71` |
| Repair sub-backup (36B) | `/opt/worldcup-predictor/backups/phase36b-repair-20260620-161016/` |

---

## 2. Files Deployed

### Backend overlay (`worldcup_predictor/`)

- **36C:** `config/env_loading.py`, `config/settings.py`, `config/provider_readiness.py`
- **36B:** `automation/worldcup_background/stale_prediction_policy.py`, `prediction_store_guard.py`, prediction store/cache invalidation columns, `scripts/repair_placeholder_predictions.py`
- **37A:** `access/admin_gate.py`, `api/deps.py`, `api/routes/admin_gate.py`, `api/routes/admin.py`, `api/web_auth.py`, `database/postgres/enums.py`

### Scripts

- `scripts/diagnose_env_providers.py`
- `scripts/validate_phase36c_env_wiring.py`
- `scripts/validate_phase36b_placeholder_repair.py`
- `scripts/validate_phase37a_admin_security.py`
- `scripts/validate_phase34b_stale_confidence_cache_fix.py`
- `scripts/validate_phase35_accuracy_driven_optimization.py`
- `scripts/repair_placeholder_predictions.py`
- `scripts/deploy_phase37b_production.sh`

### Database

- `alembic/versions/002_super_admin_role.py`

### systemd

- `deployment/systemd/worldcup-api.service` (includes `APP_ENV=production`)

### Frontend

- Built Vite dist → `/var/www/worldcup/frontend/dist`
- Source overlay → `base44-d/src/` (for on-server validation; includes AdminRoute, SuperAdminRoute, role-gated sidebar)

---

## 3. Migration Result

```
alembic upgrade head
Running upgrade 001_saas_initial -> 002_super_admin_role
```

**PostgreSQL `user_role` enum:**

```
user
admin
super_admin
```

No migration errors.

---

## 4. Environment Diagnostic (yes/no — no secrets)

| Field | Production |
|-------|------------|
| APP_ENV | production |
| loaded_env_file | .env.production |
| API_FOOTBALL_KEY_present | yes |
| SPORTMONKS_API_KEY_present | yes |
| THE_ODDS_API_KEY_present | no |
| WEATHER_API_KEY_present | no |
| DATABASE_URL_present | yes |
| production_prediction_allowed | yes |

Admin keys:

| Key | Status |
|-----|--------|
| ADMIN_ACCESS_KEY | configured (generated on deploy) |
| SUPER_ADMIN_ACCESS_KEY | configured (generated on deploy) |
| APP_ENV=production | set |

**Action required:** Retrieve generated admin keys from server `.env.production` via secure channel and store offline. Keys were not printed in deploy logs or this report.

---

## 5. Validation Results (production)

| Suite | Result |
|-------|--------|
| Phase 36C env wiring | **9/9 PASS** |
| Phase 36B placeholder repair | **19/19 PASS** |
| Phase 37A admin security | **32/32 PASS** |
| Phase 34B stale confidence cache | **20/20 PASS** |
| Phase 35 accuracy optimization | **29/29 PASS** |

Logs: `/opt/worldcup-predictor/backups/deploy-phase37b-20260620-160831/validate_phase*.log`

---

## 6. Fixture 1489393 — Before / After

### Before repair (stored row)

| Field | Value |
|-------|-------|
| source | manual |
| reason | `provider_env_missing_placeholder` |
| confidence | ~3% (legacy placeholder; pre-repair GET returned empty during deploy window) |
| is_placeholder | true (implicit via stale policy) |

### After repair

| Field | Value |
|-------|-------|
| invalidated | 1 row |
| refreshed | 1 row |
| confidence | **49.0%** |
| is_placeholder | **false** |
| prediction | home |
| cache_source (GET) | sqlite_store |
| api_football_configured | yes |
| sportmonks_configured | yes |
| loaded_env_file | .env.production |

Second GET reused SQLite cache at same confidence (49.0%).

---

## 7. Admin Security Smoke Tests

| Test | Result |
|------|--------|
| `GET /api/health` | 200 `{"status":"ok"}` |
| `GET /api/admin/health` (no auth) | **401** |
| `POST /api/admin/gate/verify` (no auth) | **401** |
| Admin gate wrong key (validated in 37A suite) | 403 + lockout after 5 failures |
| Admin gate correct key (validated in 37A suite) | gate token issued |
| Frontend sidebar (37A source checks) | Admin/Super Admin hidden for normal users |
| API Settings | gated to admin/super_admin |
| Secrets in audit/log output | none detected |

**Services:** `worldcup-api` active, `nginx` active

---

## 8. Known Issues / Notes

1. **Deploy script fix:** Initial run failed on `.env.production` permissions (`chmod 600` as root blocked `www-data`). Fixed to `640` + `www-data` ownership. Script updated locally for future deploys.
2. **Pre-repair GET snapshot empty:** API was restarting when before-snapshot curl ran; repair script independently confirmed bad row and succeeded.
3. **POST force_refresh curl empty:** Unauthenticated POST during smoke returned empty body; repair script already performed refresh. Cached GET confirmed good state.
4. **`.cache` permissions:** Ensured `www-data` owns `/opt/worldcup-predictor/.cache` (prior PermissionError on lineup cache writes).
5. **THE_ODDS_API_KEY / WEATHER_API_KEY:** not configured — expected; does not block production predictions.

---

## 9. Rollback Plan

1. Stop API: `systemctl stop worldcup-api`
2. Restore SQLite:  
   `cp /opt/worldcup-predictor/backups/deploy-phase37b-20260620-160831/football_intelligence.db /opt/worldcup-predictor/data/`
3. Restore frontend:  
   `cp -a .../frontend_dist/. /var/www/worldcup/frontend/dist/`
4. Restore repo snapshot:  
   `tar xzf .../repo_snapshot_pre.tar.gz -C /opt/worldcup-predictor`
5. Restore PostgreSQL (if needed):  
   `pg_restore -d $DATABASE_URL --clean .../postgres.dump`
6. Restore systemd unit from backup if changed
7. Restart: `systemctl restart worldcup-api nginx`

PostgreSQL `super_admin` enum value is safe to leave in place after rollback.

---

## 10. Final Production Status

| Component | Status |
|-----------|--------|
| Env loading (36C) | Live — `.env.production` loaded, keys present |
| Placeholder guard (36B) | Live — storage guard + stale policy active |
| Fixture 1489393 | Repaired — 49.0% confidence, non-placeholder |
| Admin security (37A) | Live — role + gate on admin APIs and frontend routes |
| Alembic | At head (`002_super_admin_role`) |
| Prediction engine / WDE / adaptive / fusion | Unchanged |
| Phase 36C/36B env logic | Unchanged from local implementation |

**Deploy completed:** 2026-06-20 16:10 UTC  
**Next steps (out of scope):** Assign `super_admin` role to designated operator in PostgreSQL; distribute admin keys securely; optional Sportmonks/xG phases when approved.
