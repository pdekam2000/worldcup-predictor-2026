# PHASE 36C + 36B — ENV WIRING FIX + PLACEHOLDER PREDICTION REPAIR

**Date:** 2026-06-20  
**Mode:** Implement → Validate → Report (no production deploy in this phase)  
**Status:** **READY FOR DEPLOY APPROVAL**

---

## Executive Summary

Phase **36C** fixes production environment loading so CLI, validation, background jobs, and API all resolve the same provider keys. Phase **36B** adds safe invalidation metadata, blocks storing provider-missing placeholder predictions, and provides a repair script for affected SQLite rows.

| Goal | Status |
|------|--------|
| Unified env loading (OS → ENV_FILE → `.env.production` → `.env`) | ✅ Implemented |
| Deploy/validation fails without `API_FOOTBALL_KEY` | ✅ Implemented |
| Placeholder rows from no-key runs rejected by stale policy | ✅ Fixed |
| Storage guard prevents overwriting good predictions | ✅ Implemented |
| Fixture 1489393 non-placeholder repair validated locally | ✅ 71.4% confidence, `is_placeholder=false` |
| WDE / adaptive / fusion unchanged | ✅ Preserved |

---

## Root Cause (from Phase 36A)

1. Production `.env` was **empty (0 bytes)**; `Settings` loaded `.env` only.
2. API keys lived in `.env.production` (systemd `EnvironmentFile` for `worldcup-api` only).
3. Phase 34B deploy validation ran CLI **without** sourcing `.env.production` → placeholder pipeline → **3%** stored to SQLite.
4. Stale policy accepted 34b-v1 placeholder payloads when adaptive trace existed.

---

## Phase 36C — Env Loading Policy

**Priority (pydantic-settings; OS env always wins over file values):**

1. Real OS environment variables  
2. `ENV_FILE` if set and non-empty  
3. `.env.production` when `APP_ENV=production` or `ENVIRONMENT=production`  
4. `.env` as local/dev fallback  

**Implementation:** `worldcup_predictor/config/env_loading.py` + updated `get_settings()` in `settings.py`.

### Diagnostic (yes/no only — no secrets)

```bash
python scripts/diagnose_env_providers.py
```

**Local sample output:**

| Field | Value |
|-------|-------|
| APP_ENV | local |
| loaded_env_file | `.env` |
| API_FOOTBALL_KEY_present | yes |
| SPORTMONKS_API_KEY_present | yes |
| THE_ODDS_API_KEY_present | yes |
| WEATHER_API_KEY_present | yes |
| DATABASE_URL_present | yes |
| production_prediction_allowed | yes |

### systemd (expected production)

| Service | EnvironmentFile | APP_ENV |
|---------|-----------------|---------|
| `worldcup-api.service` | `/opt/worldcup-predictor/.env.production` | `production` (added) |
| `worldcup-daily-predict.service` | same | `production` (added) |

Deploy script now runs all validations with:

```bash
set -a && source .env.production && set +a
APP_ENV=production
```

---

## Phase 36B — Placeholder Repair

### Schema (minimal migration)

Added to `worldcup_stored_predictions`:

| Column | Purpose |
|--------|---------|
| `is_active` | 0 = invalidated, 1 = active |
| `invalidated_at` | UTC timestamp |
| `invalidated_reason` | e.g. `provider_env_missing_placeholder` |
| `superseded_by` | optional fixture id reference |

### Repair script

```bash
# Dry run
python scripts/repair_placeholder_predictions.py --dry-run

# Repair (backs up SQLite first)
python scripts/repair_placeholder_predictions.py --fixture-id 1489393
```

Backup directory pattern: `backups/phase36b-repair-<timestamp>/`

### Stale policy update

- **Removed** 34b-v1 bypass that ignored `placeholder_data` no_bet reasons.
- Payloads with `provider_env_missing`, `is_placeholder=true`, or provider-env placeholder evidence are **invalid** for serve/cache.
- Low-confidence + high-probability mismatch no longer auto-valid just because adaptive trace exists.

### Storage guard

Before SQLite/file cache write:

- Reject if `API_FOOTBALL_KEY` missing → `provider_env_missing`
- Reject provider placeholder payloads → `provider_env_missing_placeholder`
- Do not overwrite existing non-placeholder with worse placeholder → `would_downgrade_existing_non_placeholder`
- Diagnostic shadow log: `data/shadow/provider_env_missing_predictions.jsonl`

---

## Fixture 1489393 — Before / After

| Field | Before (Phase 34B no-env validation) | After (36B local repair) |
|-------|----------------------------------------|---------------------------|
| is_placeholder | **true** | **false** |
| confidence | **3.0%** | **71.4%** |
| data_quality | 65% | ~85% |
| WDE final | 11.5 | 62.7 |
| provider_readiness.api_football_configured | false / missing | **true** |
| prediction_engine_version | 34b-v1 | 34b-v1 |
| national_team_intelligence.version | 32e | 32e |
| adaptive_confidence_trace | present | present |
| Cache reuse on second request | N/A | ✅ same confidence |

---

## Files Changed

### New

| File | Purpose |
|------|---------|
| `worldcup_predictor/config/env_loading.py` | Env file resolution |
| `worldcup_predictor/config/provider_readiness.py` | Key checks, diagnostic, stamping |
| `worldcup_predictor/automation/worldcup_background/prediction_store_guard.py` | Storage guard |
| `scripts/diagnose_env_providers.py` | Safe env diagnostic |
| `scripts/repair_placeholder_predictions.py` | Backup + invalidate + refresh |
| `scripts/validate_phase36c_env_wiring.py` | 36C validation |
| `scripts/validate_phase36b_placeholder_repair.py` | 36B validation |

### Updated

| File | Change |
|------|--------|
| `worldcup_predictor/config/settings.py` | Dynamic env file in `get_settings()` |
| `worldcup_predictor/automation/worldcup_background/stale_prediction_policy.py` | Reject provider placeholders |
| `worldcup_predictor/automation/worldcup_background/prediction_store.py` | Guard on upsert; lazy cache import |
| `worldcup_predictor/quota/prediction_cache.py` | Guard on store; lazy guard import |
| `worldcup_predictor/automation/worldcup_background/prediction_runner.py` | Assert keys; stamp readiness |
| `worldcup_predictor/api/prediction_metadata.py` | Provider readiness + is_placeholder stamp |
| `worldcup_predictor/api/routes/predictions.py` | Pass placeholder flag to store |
| `worldcup_predictor/database/migrations.py` | Phase 36C columns |
| `worldcup_predictor/database/repository.py` | Invalidate/upsert/list helpers |
| `scripts/validate_phase34b_stale_confidence_cache_fix.py` | Require API key; reject 3% placeholder |
| `scripts/deploy_phase34b_35_server.sh` | Source `.env.production`; 36C/36B validation |
| `deployment/systemd/worldcup-api.service` | `APP_ENV=production` |
| `deployment/systemd/worldcup-daily-predict.service` | `APP_ENV=production` |

### Not touched (per charter)

- WDE weights (`weighted_decision_engine.py`)
- Adaptive confidence math
- Fusion penalty caps (`final_decision_fusion_engine_v2.py`)
- Frontend

---

## Validation Results (Local)

| Suite | Result |
|-------|--------|
| Phase 36C env wiring | **9/9 PASS** |
| Phase 36B placeholder repair | **19/19 PASS** |
| Phase 34B stale cache (updated) | **18/18 PASS** |
| Phase 35 accuracy optimization | **29/29 PASS** |

---

## Bad Rows (Local DB after repair)

| Metric | Count |
|--------|-------|
| Bad rows found (dry-run post-repair) | **0** |
| Invalidated in validation run | 1 (1489393 test row) |
| Refreshed | 1 |
| Local backup | Created during `repair_placeholder_predictions.py` / validation pipeline |

---

## Production Deployment Checklist (when approved)

1. Backup `/opt/worldcup-predictor/data/football_intelligence.db`
2. Deploy code overlay
3. Update systemd units (`APP_ENV=production`)
4. `systemctl daemon-reload && systemctl restart worldcup-api`
5. Run on server:
   ```bash
   cd /opt/worldcup-predictor
   set -a && source .env.production && set +a
   export APP_ENV=production
   python scripts/diagnose_env_providers.py
   python scripts/validate_phase36c_env_wiring.py
   python scripts/repair_placeholder_predictions.py --fixture-id 1489393
   python scripts/validate_phase36b_placeholder_repair.py
   ```
6. Confirm `/api/health` OK
7. GET `/api/predict/1489393` → confidence > 15%, `is_placeholder=false`

---

## Rollback Plan

1. Restore SQLite from `backups/phase36b-repair-*` or pre-deploy backup  
2. Revert code to prior commit  
3. Restart `worldcup-api`  
4. Old stale policy returns — placeholder 3% rows may reappear if not repaired; keep backup until verified  

---

## Production Status

| Item | Status |
|------|--------|
| Code implemented locally | ✅ |
| Local validation | ✅ All pass |
| Production deploy | ⏸ **Not executed** (awaiting approval) |
| Sportmonks / fusion calibration | ⏸ Out of scope (per instruction) |

---

*End of Phase 36C + 36B report.*
