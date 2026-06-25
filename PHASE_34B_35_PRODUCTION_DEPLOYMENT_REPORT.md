# PHASE 34B + 35 — PRODUCTION DEPLOYMENT REPORT

**Date:** 2026-06-20  
**Server:** `91.107.188.229` / `https://footballpredictor.it.com`  
**Deploy method:** Scoped tarball overlay + hotfix patches  
**Status:** **DEPLOYED**

---

## Executive Summary

Phase **34B** fixes stale/placeholder confidence cache invalidation and adds full adaptive confidence tracing. Phase **35** Accuracy Driven Optimization (Learning Report V2, admin charts, analytics) is deployed alongside 34B.

| Component | Status |
|-----------|--------|
| Stale cache invalidation (pre-34b payloads) | ✅ Live |
| Engine version stamps on all new predictions | ✅ `34b-v1` |
| Adaptive + fusion confidence trace | ✅ Stored in payload + audit_trace |
| UI model confidence vs outcome probability labels | ✅ Frontend deployed |
| Phase 35 optimization engine + admin learning | ✅ Live |
| Phase 32E / 33 / 33B / 34 preserved | ✅ Regressions pass |

---

## 1. Root Cause Summary (Phase 34A → 34B)

| Issue | Root cause | 34B fix |
|-------|------------|---------|
| UI showed **3% confidence** | Not a frontend bug — API stored `confidence: 3.0` | Invalidates unstamped stale cache; traces full pipeline |
| Stale **background_daily** cache | Old payloads lacked engine version + adaptive trace | `is_stored_prediction_quality_valid()` rejects legacy rows |
| **11.5% WDE → 3%** unexplained | Fusion engine post-adaptive overwrite (−10 pts, Weak band) | `fusion_adjustment` + `fusion_confidence_after` in adaptive trace |
| **51.7% home win vs 3% confidence** | Different concepts (probability vs model trust) | UI labels + help text |
| Local **71%** vs prod **3%** | Production `is_placeholder=True` + fusion; local has live data | Stale cache invalidated; fresh prod run documented with trace |

---

## 2. Files Changed

### Phase 34B (new)
- `worldcup_predictor/prediction/engine_versions.py`
- `worldcup_predictor/automation/worldcup_background/stale_prediction_policy.py`
- `worldcup_predictor/api/prediction_metadata.py`

### Phase 34B (updated)
- `worldcup_predictor/automation/worldcup_background/freshness.py` *(via store integration)*
- `worldcup_predictor/automation/worldcup_background/prediction_store.py`
- `worldcup_predictor/automation/worldcup_background/prediction_runner.py`
- `worldcup_predictor/quota/prediction_cache.py`
- `worldcup_predictor/api/audit_trace_helpers.py`
- `worldcup_predictor/api/routes/predictions.py`
- `base44-d/src/pages/PredictionDetail.jsx`
- `scripts/validate_phase34b_stale_confidence_cache_fix.py`

### Phase 35 (deployed)
- `worldcup_predictor/admin/accuracy_optimization.py`
- `worldcup_predictor/admin/learning_engine.py`
- `worldcup_predictor/api/routes/admin_accuracy.py`
- `base44-d/src/pages/AdminLearningDashboard.jsx`
- `base44-d/src/api/saasApi.js`
- `scripts/validate_phase35_accuracy_driven_optimization.py`

### Validation updates
- `scripts/validate_phase34_admin_accuracy_learning_subscription.py` — stamp test payloads
- `scripts/validate_phase33b_no_bet_ux_replacement.py` — stamp test payloads
- `scripts/deploy_phase34b_35_server.sh`

---

## 3. Backup

| Asset | Path |
|-------|------|
| **Backup directory** | `/opt/worldcup-predictor/backups/deploy-phase34b-35-20260620-153639` |
| Pre-deploy commit | `267812e6e1c71258b78373161ade915c00b3ed71` |
| SQLite DB | `.../football_intelligence.db` |
| Frontend dist | `.../frontend_dist/` |
| Pre-deploy overlay | `.../repo_overlay_pre.tar.gz` |
| Health snapshot | `.../health.json` |

---

## 4. Validation Results (Production)

| Suite | Result |
|-------|--------|
| Phase 34B stale cache fix | **17/17 PASS** |
| Phase 35 accuracy optimization | **29/29 PASS** |
| Phase 33 background prediction | **21/21 PASS** |
| Phase 33B caution UX | **20/20 PASS** |
| Phase 34 admin/learning/subscription | **32/32 PASS** |
| `/api/health` | ✅ `{"status":"ok"}` |
| Admin routes (unauthenticated) | 401 (expected — auth required) |

---

## 5. Fixture 1489393 — Before / After

### Before (stale cache — Phase 34A)

| Field | Value |
|-------|-------|
| `confidence` | **3.0** (unexplained) |
| `prediction_engine_version` | missing |
| `adaptive_confidence_trace` | missing |
| `cache_source` | `background_daily` |
| WDE final (audit only) | 11.5 |
| Served from SQLite | ✅ (stale) |

### After (34B refresh on production)

| Field | Value |
|-------|-------|
| `confidence` | **3.0** (fusion-adjusted — now traced) |
| `prediction_engine_version` | **34b-v1** |
| `national_team_intelligence.version` | **32e** |
| `adaptive_confidence_version` | **1-v1** |
| `cache_source` | `phase34b_refresh` |
| WDE baseline → final | 27.5 → 11.5 |
| Adaptive | 11.5 → **13.0** (+1.5 similar matches) |
| Fusion (Weak) | 13.0 → **3.0** (−10.0) |
| SQLite serve after refresh | ✅ with full trace |

> **Note:** Production pipeline still yields **3% model confidence** for this fixture due to placeholder intelligence + fusion — but it is no longer an *unexplained stale cache*. Local non-placeholder run yields ~**71%**. Follow-up: resolve production placeholder data for World Cup fixtures (separate from 34B).

---

## 6. Adaptive Confidence Trace Example (1489393)

```json
{
  "confidence_before_adaptive": 11.5,
  "adaptive_adjustment": 1.5,
  "confidence_after_adaptive": 13.0,
  "adaptive_reasons": "52 similar matches found. Historical success rate: 56%.; similar matches +1.5; fusion (Weak) adjusted confidence to 3.0%",
  "fusion_confidence_after": 3.0,
  "fusion_adjustment": -10.0,
  "similar_sample_size": 52
}
```

Stored in:
- `adaptive_confidence_trace` (top-level)
- `audit_trace.confidence.adaptive`
- `audit_trace.confidence.baseline/final/reductions/no_bet_reasons`

---

## 7. Phase 35 Dashboard Status

| Endpoint | Status |
|----------|--------|
| `GET /api/admin/learning/dashboard` | ✅ Deployed (admin auth) |
| `GET /api/admin/learning/optimization` | ✅ Deployed |
| `POST /api/admin/learning/reports/generate?version=v2` | ✅ Stores `advisory_v2` |
| `/admin/learning` UI | ✅ Charts: confidence buckets, markets, recommendations, agents, calibration |

**Rules preserved:** Analytics only — no WDE threshold changes, no NTI scoring changes, no new Sportmonks features.

---

## 8. Invalidation Rules (34B)

Stored predictions are **rejected** (cache miss → refresh on next request) when:

- Missing `prediction_engine_version` (`34b-v1`)
- Missing `national_team_intelligence.version` (`32e`)
- Legacy `background_daily` without current engine stamp
- Missing adaptive trace with unexplained WDE→stored confidence drop (>5 pts)
- Low confidence + high probability **without** adaptive trace (stale artifact)

Current-engine payloads **with** adaptive trace may store low confidence (e.g. 3%) when fusion legitimately reduces it.

---

## 9. Rollback Plan

```bash
# On server 91.107.188.229
BACKUP=/opt/worldcup-predictor/backups/deploy-phase34b-35-20260620-153639
cd /opt/worldcup-predictor

# Restore SQLite
cp -a $BACKUP/football_intelligence.db data/football_intelligence.db

# Restore frontend
cp -a $BACKUP/frontend_dist/. /var/www/worldcup/frontend/dist/

# Restore backend overlay (extract pre tarball or git checkout files)
tar xzf $BACKUP/repo_overlay_pre.tar.gz -C /opt/worldcup-predictor

systemctl restart worldcup-api
curl -sf http://127.0.0.1:8000/api/health
```

---

## 10. Final Production Status

| Check | Status |
|-------|--------|
| API healthy | ✅ |
| Stale 3% cache invalidated | ✅ |
| New predictions version-stamped | ✅ |
| Adaptive + fusion trace stored | ✅ |
| Phase 35 admin learning live | ✅ |
| Frontend confidence labels | ✅ |
| Regressions 33/33B/34 | ✅ |

### Known follow-up (not blocking 34B/35)

1. Production placeholder intelligence for WC fixtures (`is_placeholder=True`) — depresses WDE baseline
2. Fusion post-adaptive −10 pt drop on weak band — now traced; tuning deferred
3. `GET /api/predict/{id}` returns 404 without auth when cache miss — POST requires login (Phase 34 quota)

---

**STOP — Phase 34B + 35 deployed and reported.**
