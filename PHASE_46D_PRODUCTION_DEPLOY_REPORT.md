# Phase 46D — Production Deploy Report

**Date:** 2026-06-21 UTC  
**Server:** `91.107.188.229`  
**App path:** `/opt/worldcup-predictor`  
**PHASE_46D_STATUS:** PRODUCTION_ACTIVE

---

## Deploy Timeline

| Step | Time (UTC) | Result |
|------|------------|--------|
| Initial deploy | 20260621-205326 | Validation 13/13 PASS; smoke 6/7 FAIL (circular import) |
| Hotfix deploy | 20260621-2058xx | Circular import fix applied |
| Re-validation | Post-restart | Validation 13/13 PASS; smoke 7/7 PASS |

**Backup path:** `/opt/worldcup-predictor/backups/deploy-phase46d-20260621-205326`

---

## Deploy Steps Executed

1. **Full backup**
   - Git commit hash captured
   - `data/football_intelligence.db` copied
   - `.env.production` copied

2. **Extract tarball**
   - `worldcup_predictor/intelligence/provider_utilization/` (full package)
   - `enrichment_service.py`, `odds_movement_agent.py`, `weighted_decision_engine.py`
   - `migrations.py`, `repository.py`
   - Validation, smoke, and deploy scripts
   - `PROVIDER_FIELD_INVENTORY.md`, `PROVIDER_FUSION_POLICY.md`

3. **Restart API**
   - `systemctl restart worldcup-api` → **active**

4. **Reload nginx**
   - `nginx -t` → OK
   - `systemctl reload nginx`

5. **Validation**
   - `scripts/validate_phase46d_provider_utilization.py` → **13/13 PASS**

6. **Production smoke**
   - `scripts/phase46d_production_smoke.py` → **7/7 PASS**

---

## Smoke Test Results (Production)

| Check | Status | Detail |
|-------|--------|--------|
| `api_health` | PASS | `{"status":"ok"}` |
| `accuracy_performance` | PASS | HTTP 200 |
| `history_route` | PASS | HTTP 401 (auth required — expected) |
| `api_football_client` | PASS | Configured |
| `sportmonks_client` | PASS | Checked |
| `provider_utilization_module` | PASS | Import + event parse OK |
| `billing_route` | PASS | HTTP 401 (auth required — expected) |

---

## Issue Encountered & Resolution

**Problem:** Circular import on production smoke

```
odds_movement_intelligence → odds_control_agent → orchestrator → odds_movement_agent → odds_movement_intelligence
```

**Fix:**

1. Inlined `_implied_from_decimal()` in `odds_movement_intelligence.py` (removed agents import)
2. Lazy-imported `build_odds_movement_intelligence` inside `OddsMovementAgent.run()`

**Post-fix:** All smoke checks pass; API stable.

---

## Preserved Systems (Verified)

| System | Status |
|--------|--------|
| Prediction engine | Unchanged |
| WDE factor weights | Unchanged (0.1 verified) |
| History / archive | Routes respond |
| Evaluation pipeline | 1X2 + goal minute eval unchanged |
| Billing | Route responds |
| Weather | Not modified in 46D |
| Stripe Live | Not modified in 46D |

---

## Database Migration

`PHASE46D_DDL` applied on startup via `ensure_schema_compat()`:

- Table: `fixture_unified_events`
- Index: `idx_fixture_unified_events_fixture`

No destructive migrations.

---

## Rollback Procedure

If rollback required:

```bash
cd /opt/worldcup-predictor
cp backups/deploy-phase46d-20260621-205326/football_intelligence.db data/football_intelligence.db
git checkout -- worldcup_predictor/
systemctl restart worldcup-api
```

---

## Post-Deploy Monitoring

Recommended checks (first 24h):

- New fixtures show `provider_utilization_v1` in supplemental sources
- `fixture_unified_events` rows appear for completed fixtures with events
- Odds movement agent signals include 46D intelligence fields
- No regression in `/api/performance/summary` accuracy metrics

---

**Deploy outcome: SUCCESS — PRODUCTION_ACTIVE**
