# Phase 27 — Fixes Report

**Project:** WorldCup Predictor 2026  
**Date:** 2026-06-20  
**Status:** Implemented — awaiting deploy approval  
**Constraints preserved:** No WDE weight changes, no calibration, promotion modes remain `shadow`, no DB migrations, no destructive DB changes

---

## Summary

Phase 27 fixes address the post-deploy gap where the Specialist Analysis UI showed only 18 legacy agents when serving **stale pre-deploy prediction cache**. The backend already ran all 22 specialists on fresh predictions; the fixes ensure stale cache is rejected, Phase 22 agents are labeled in the UI, and safe promotion/audit trace is exposed via API.

| Task | Status |
|------|--------|
| 1. Cache invalidation / version bump | **Done** |
| 2. Frontend labels/icons | **Done** |
| 3. API audit trace exposure | **Done** |
| 4. Sportmonks enrichment follow-up | **Partial** (low-risk fixes + pending items) |
| 5. Frontend rebuild | **Built locally** — deploy steps below |

---

## Files Changed

| File | Change |
|------|--------|
| `worldcup_predictor/quota/prediction_cache_policy.py` | **NEW** — schema version `27-v1`, agent-count validation, Phase 22 required keys |
| `worldcup_predictor/quota/prediction_cache.py` | Reject invalid cache entries; stamp schema on store |
| `worldcup_predictor/api/audit_trace_helpers.py` | **NEW** — safe `audit_trace` builder (no secrets/raw payloads) |
| `worldcup_predictor/api/routes/predictions.py` | Attach `audit_trace` to success payload; hydrate trace on cache hit |
| `worldcup_predictor/providers/sportmonks_consumption.py` | Prefer complete SQLite SM payload over lookup fallback metadata |
| `worldcup_predictor/providers/sportmonks_enrichment.py` | Force refresh when SQLite row has incomplete includes |
| `base44-d/src/pages/PredictionDetail.jsx` | Phase 22 labels; Promotion Trace panel |
| `scripts/validate_phase27_fixes.py` | **NEW** — Phase 27 validation |
| `scripts/validate_quota_protection.py` | Updated cache roundtrip test for schema v27 |

---

## 1. Cache Behavior

### Schema marker

New fields on stored prediction payloads:

```json
{
  "cache_schema_version": "27-v1",
  "specialist_agent_count": 22
}
```

### Validation rules (`is_prediction_cache_valid`)

A cached prediction is **rejected** (treated as cache miss) when:

- `cache_schema_version` ≠ `27-v1`
- `specialist_summary.agents` count < **22** (current orchestrator minus master)
- Any Phase 22 key missing:
  - `expected_lineup_agent`
  - `tournament_context_agent`
  - `xg_intelligence_agent`
  - `sportmonks_prediction_agent`

### Runtime effect

| Endpoint | Old 18-agent cache | Fresh 22-agent cache |
|----------|-------------------|---------------------|
| `GET /api/predict/{id}` | **404 not_cached** (auto-invalidate) | **200** with full payload |
| `POST /api/predict/{id}` | Cache miss → pipeline re-run → new 22-agent payload stored | Cache hit (if TTL valid) |

**Safe fallback:** Invalid cache never returns partial specialist data; client falls through to Run Prediction / POST pipeline.

### Local validation

```bash
python scripts/validate_phase27_fixes.py
python scripts/validate_quota_protection.py
```

Results: **10/10** Phase 27 checks pass; **16/16** quota checks pass.

---

## 2. API Response Changes

### New top-level field: `audit_trace`

Added to successful `POST /api/predict/{id}` responses and hydrated on valid cache hits.

**Includes (safe subset only):**

- `promotion_modes` — all promotion flags (`expected_lineup`, `tournament_context`, `xg`, `sportmonks_prediction`, `lambda_bridge`, `rule_a_gate`, `real_world_validation`)
- Per-agent blocks: `expected_lineup`, `tournament_context`, `xg_intelligence`, `sportmonks_prediction`
  - Agent `status`, `impact_score`, `domain`, `status_reason`
  - Promotion `mode`, `shadow_active`, `gated_active`, `promotion_applied`, `delta_score`, `reason`
- `combined_promotion_confidence_delta`
- `confidence` block (baseline/final/caps/reductions/no_bet_reasons) when WDE trace available

**Excludes:** API keys, tokens, raw Sportmonks/API-Football payloads, provider response bodies.

### Example shape (abbreviated)

```json
{
  "status": "ok",
  "fixture_id": 1539007,
  "cache_schema_version": "27-v1",
  "specialist_agent_count": 22,
  "specialist_summary": { "agents": { "...": "22 keys" } },
  "audit_trace": {
    "cache_schema_version": "27-v1",
    "promotion_modes": {
      "expected_lineup": "shadow",
      "tournament_context": "shadow",
      "xg": "shadow",
      "sportmonks_prediction": "shadow"
    },
    "expected_lineup": {
      "status": "available",
      "mode": "shadow",
      "promotion_applied": false,
      "delta_score": 0.0
    }
  }
}
```

### Shadow flags

Unchanged — defaults remain `shadow` in `settings.py`. `audit_trace.promotion_modes` reflects env values; no gated promotion enabled.

---

## 3. Frontend Changes

### Specialist labels (`PredictionDetail.jsx`)

| Agent key | Label |
|-----------|-------|
| `expected_lineup_agent` | Expected Lineup Specialist |
| `tournament_context_agent` | Tournament Context Specialist |
| `xg_intelligence_agent` | Sportmonks xG Specialist |
| `sportmonks_prediction_agent` | Sportmonks Prediction Specialist |

Icons: generic `Brain` fallback (per spec).

### Promotion Trace panel

New section renders when `audit_trace` is present — shows shadow-mode promotion status per Phase 22/24 track.

### Build

```bash
cd base44-d && npm run build
```

Local build: **success** (Vite).

---

## 4. Sportmonks Enrichment Follow-Up

### Root causes (audit)

| Agent | Typical unavailable reason |
|-------|---------------------------|
| `sportmonks_prediction_agent` | Enrichment fetch failed → **lookup fallback** payload lacks `odds`/`predictions` includes |
| `xg_intelligence_agent` | Same fallback lacks `xGFixture` include (xG add-on / pre-match window) |

Production log observed: `Sportmonks enrichment failed for fixture … — using lookup fallback payload`.

### Low-risk fixes implemented

1. **`_resolve_raw_fixture_data`** — Prefer SQLite row with **complete** Phase 22C/22D includes over `provider_metadata.sportmonks_fixture` lookup fallback.
2. **Unified enrichment path** — When SQLite row exists but includes incomplete, **force refresh** enrichment (one API call) before falling back to lookup payload.

### Pending (not implemented — quota / plan risk)

- Sportmonks API enrichment hard failures on production (needs live error inspection)
- xG add-on plan verification for WC league 732
- Pre-match window timing for `xGFixture` population
- Re-fetch policy when lookup fallback was previously cached in `provider_metadata`

**Recommendation:** After deploy, run one `POST /api/predict/1539007?force_refresh=true` (admin) and check orchestrator audit for SM agent status. If still unavailable, inspect `journalctl -u worldcup-api` for Sportmonks HTTP errors.

---

## 5. Validation Results

### Automated (local)

| Script | Result |
|--------|--------|
| `scripts/validate_phase27_fixes.py` | 10/10 PASS |
| `scripts/validate_quota_protection.py` | 16/16 PASS |
| `base44-d` `npm run build` | PASS |

### Production acceptance (post-deploy)

Run on Hetzner after deploy:

```bash
# 1. Restart API
sudo systemctl restart worldcup-api

# 2. Fresh predict — must show 22 agents
python scripts/audit_phase5_fixture.py http://127.0.0.1:8000 1539007

# 3. Confirm Phase 22 keys present
# expected_lineup_agent, tournament_context_agent,
# xg_intelligence_agent, sportmonks_prediction_agent

# 4. Confirm stale cache rejected (fixture with old 18-agent file → 404 GET or re-run POST)
python scripts/validate_phase27_fixes.py
```

**Expected for fixture 1539007 (fresh POST):**

- `agent_count`: 22  
- Phase 22 agents present in `specialist_summary.agents`  
- `cache_schema_version`: `27-v1`  
- `audit_trace.promotion_modes.*`: `shadow`  
- UI: 22 specialist cards + Promotion Trace panel  

**Stale cache behavior:**

- Fixtures previously cached with 18 agents → `GET` returns 404 → user clicks Run Prediction → fresh 22-agent payload

---

## Deployment Instructions

### Backend (Hetzner)

```bash
cd /opt/worldcup-predictor
git pull   # or rsync Phase 27 changes
source .venv/bin/activate
pip install -r requirements.txt   # if deps unchanged, skip
set -a && source .env.production && set +a
python scripts/validate_phase27_fixes.py
sudo systemctl restart worldcup-api
journalctl -u worldcup-api -n 50 --no-pager
```

**No Alembic migration required.** Old cache files remain on disk but are ignored by validation (cache miss).

Optional: clear stale prediction files (non-destructive to DB):

```bash
rm -f /opt/worldcup-predictor/.cache/predictions/*.json
```

### Frontend

```bash
cd /opt/worldcup-predictor/base44-d
npm ci
npm run build
sudo rsync -a dist/ /var/www/worldcup/frontend/dist/
```

Verify static bundle date updates:

```bash
stat /var/www/worldcup/frontend/dist/index.html
```

### Smoke test (browser)

1. Open Match Center → fixture **1539007** (or any WC fixture).
2. Run Prediction (or Refresh if cached).
3. Confirm Specialist Analysis shows **22 cards** including:
   - Expected Lineup Specialist  
   - Tournament Context Specialist  
   - Sportmonks xG Specialist  
   - Sportmonks Prediction Specialist  
4. Confirm **Promotion Trace** section appears below specialists.
5. Open a fixture that previously showed 18 agents only — should prompt re-run or auto-fetch fresh data.

---

## Settings / Safety Checklist

| Item | Status |
|------|--------|
| WDE weights | Unchanged |
| Calibration | Unchanged |
| `EXPECTED_LINEUP_PROMOTION_MODE` | Default `shadow` |
| `TOURNAMENT_CONTEXT_PROMOTION_MODE` | Default `shadow` |
| `XG_PROMOTION_MODE` | Default `shadow` |
| `SPORTMONKS_PREDICTION_PROMOTION_MODE` | Default `shadow` |
| Database schema | Unchanged |
| API secrets in responses | Excluded |

---

## Stop Point

Phase 27 fixes are complete per approved scope. **No further changes** until explicit approval.

Next optional phases (not started):

- Dedicated `/api/predict/{id}/audit` endpoint
- Sportmonks enrichment failure diagnostics on production
- Cache schema auto-bump hook tied to git/orchestrator hash

---

*End of Phase 27 fixes report.*
