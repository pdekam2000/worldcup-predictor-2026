# HOTFIX H2 — Expand Predictions Cached Data

**Date:** 2026-06-25  
**Priority:** HIGH  
**Final status:** `IMPLEMENTED_NOT_DEPLOYED` (same bundle as H1; deploy pending)

---

## Root cause

**Expand predictions** panel (`EliteMatchCard.jsx`) loaded data **only** via:

```
GET /api/predict/{fixture_id}
```

On production fixture **1489410**:

| Signal | Value |
|--------|-------|
| Match list `has_prediction` | `true` (from PredOps / stored summary) |
| `GET /api/predict/1489410` | **404 `not_cached`** |
| `GET /api/predops/snapshots/latest?fixture_id=1489410` | **200** — snapshot with `publication_overlay` + 21 markets |

The UI showed **"Could not load cached prediction."** because the Worldcup prediction store cache was empty while the immutable PredOps snapshot existed.

### Failing endpoint

Primary failure: **`GET /api/predict/{fixture_id}`** → 404  
Source of truth should be: **latest PredOps snapshot payload** (read-only fallback), then optional live POST.

---

## Data flow (fixed)

```
Match Card (has_prediction=true)
  → fixture_id
  → fetchPredictionForFixture()
       1. GET /api/predict/{id}          ← now falls back server-side to PredOps payload
       2. GET /api/predops/snapshots/latest  ← client belt-and-suspenders
       3. (optional) POST /api/predict/{id}  ← Match Detail only, allowRun
  → normalizePredictionPayload / predopsSnapshotToPrediction
  → PredictionExpandPanel → markets UI
```

---

## Mapping issue

Public PredOps sanitize strips full `payload` but retains per-market `final_selected_prediction`. Added `predopsSnapshotToPrediction()` to rebuild `detailed_markets` + `probabilities` for expand UI when only the public snapshot is available.

Backend `_predops_snapshot_as_cached()` serves the **full stored payload** on predict GET — preferred path after deploy.

---

## Files changed

| File | Change |
|------|--------|
| `base44-d/src/api/worldcupApi.js` | `fetchPredictionForFixture`, `predopsSnapshotToPrediction` |
| `base44-d/src/components/match-center/EliteMatchCard.jsx` | Uses new loader; retry button; better empty states |
| `base44-d/src/components/match-center/PredictionExpandPanel.jsx` | Bet Quality + Source Model; safe pick strings |
| `worldcup_predictor/api/routes/predictions.py` | PredOps cache fallback (no engine changes) |

---

## UX improvements

| Before | After |
|--------|-------|
| "Could not load cached prediction." | "No prediction has been generated yet." (when truly absent) |
| No retry | **Retry** button on network failure |
| Hidden bet quality / source | Bet Quality badge + Source Model line in expand panel |

Markets rendered independently — one missing market does not hide others.

---

## Validation

| Check | Pre-deploy | Post-deploy (expected) |
|-------|------------|------------------------|
| Expand loads for WC 1489410 | FAIL (404) | PASS |
| Markets visible | FAIL | PASS (from snapshot/payload) |
| Bet Quality visible | N/A | PASS |
| Source Model visible | N/A | PASS |
| Retry works | N/A | PASS |
| React object-child crash | FAIL risk | PASS (safeMarketSelection) |

Run after deploy:

```bash
SKIP_FRONTEND_BUILD=1 python scripts/validate_hotfix_h1_match_detail_logo_flags.py
bash scripts/deploy_hotfix_h1_h2_smoke.sh
```

---

## Production smoke (pending deploy)

Tarball uploaded to `root@91.107.188.229:/tmp/hotfix_h1_h2_deploy.tar.gz`.

After `deploy_hotfix_h1_h2_production.sh`:

- `GET /api/predict/1489410?competition=world_cup_2026` → **200**
- Expand panel shows markets without error string

---

## Final status target

`EXPAND_PREDICTIONS_FIXED` after production deploy confirms predict 200 + expand markets render.
