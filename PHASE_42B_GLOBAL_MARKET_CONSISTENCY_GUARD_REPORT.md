# PHASE 42B-FIX — Global Market Consistency Guard Report

**Date:** 2026-06-21  
**Phase:** 42B-FIX — Global Market Consistency Guard  
**Status:** **IMPLEMENTED & VALIDATED (NOT DEPLOYED)**

---

## Executive summary

Added a **post-processing consistency layer** that runs on every prediction API response before React Prediction Detail renders it. The guard detects cross-market contradictions (BTTS vs goalscorer, 1X2 vs correct score, etc.), withholds unsafe display fields, and preserves raw model outputs for admin audit.

**Validation:** `19/19 PASS` via `scripts/validate_phase42b_global_market_consistency_guard.py`

**Not changed:** prediction engine, WDE, model probabilities, market deletion, database migrations.

**Not deployed** — awaiting approval.

---

## Root cause

Markets were assembled independently in `build_detailed_markets()` and ranked separately in `market_ranking_engine.py`. Each market used its own signal slice, so the UI could show logically incompatible recommendations on the same fixture — for example:

- **BTTS No 81.7%** alongside a **likely goalscorer from the away team** with low xG
- **1X2 Home Win** alongside **Correct Score 1-2** (away win)
- **Under 2.5 82%** alongside **early first-goal timing (16-30')**

Existing `consistency_engine.py` **mutates** engine outputs (harmonizes 1X2/O/U to scoreline). Phase 42B-FIX intentionally avoids that — it is display-only post-processing with audit preservation.

---

## Rules implemented

| # | Rule | Action |
|---|------|--------|
| 1 | BTTS No ≥ 70% vs goalscorer from low-scoring team | **Withhold** goalscorer |
| 2 | Under 2.5 ≥ 70% vs early/aggressive goal timing | **Withhold** first-goal timing |
| 3 | Correct score winner ≠ 1X2 leader | **Withhold** conflicting score row |
| 4 | Double Chance leader excludes 1X2 leader | **Warning** on DC + **withhold** DC picks |
| 5 | BTTS No high vs both-teams-score lines; BTTS Yes high vs clean-sheet lines | **Withhold** conflicting scores |
| 6 | Goalscorer from team with low scoring probability / missing xG + weak confidence | **Withhold** goalscorer |

### Thresholds

- BTTS / Under high: **≥ 70%**
- Team low scoring: **< 35%** (Poisson from xG, or 1X2-derived fallback)
- Strong goalscorer confidence: **≥ 72%**
- Early timing bands: `0-15`, `16-30`, or expected minute **≤ 35**

### Per-market metadata (added to API)

Each guarded block includes:

```json
{
  "display_allowed": true,
  "consistency_status": "ok",
  "withheld_reason": null,
  "consistency_messages": []
}
```

Status values: `ok` | `warning` | `withheld`

Top-level audit block:

```json
{
  "consistency_guard": {
    "applied": true,
    "consistency_warnings": [],
    "withheld_markets": [],
    "raw_markets_audit": { "...": "pre-guard detailed_markets snapshot" },
    "rules_version": "42b-fix-v1"
  }
}
```

- **Regular users:** `raw_markets_audit` stripped from response  
- **Admin / super_admin:** full raw audit retained

---

## Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/prediction/market_consistency_guard.py` | **Added** — reusable guard module |
| `worldcup_predictor/api/display_helpers.py` | **Updated** — apply guard in `enrich_prediction_payload()` |
| `base44-d/src/pages/PredictionDetail.jsx` | **Updated** — respect `display_allowed`, withheld UI |
| `scripts/validate_phase42b_global_market_consistency_guard.py` | **Added** — 19-check validation |

**Untouched:** `scoring_engine.py`, `weighted_decision_engine.py`, `consistency_engine.py` (engine harmonizer), cache storage format (raw cached; guard applied at read time).

---

## Before / after examples

### Example A — BTTS No + away goalscorer (Germany vs Ivory Coast)

**Before (contradictory):**

| Market | Display |
|--------|---------|
| BTTS | No **81.7%** |
| Likely Goalscorer | Sebastien Haller (Ivory Coast) |

**After:**

| Market | Display |
|--------|---------|
| BTTS | No **81.7%** (unchanged probabilities) |
| Likely Goalscorer | *Withheld* — "This market was withheld because it conflicts with stronger model signals." |

Raw player/team preserved in `consistency_guard.raw_markets_audit` (admin only).

---

### Example B — 1X2 Home + Correct Score 1-2

**Before:** Home Win leader + top score **1-2** shown  
**After:** Score row `display_allowed: false`, reason cites 1X2 vs scoreline conflict

---

### Example C — Under 2.5 82% + early timing 16-30'

**Before:** Low goals + aggressive early-minute prediction both shown confidently  
**After:** First Goal & Timing section withheld; probabilities for O/U unchanged

---

### Example D — Consistent payload

When markets align (BTTS Yes + Germany scorer + late timing + 2-1 score matching home lean):

- All `consistency_status: ok`
- `withheld_markets: []`
- No UI change except optional consistency metadata

---

## Validation results

```
Phase 42B-FIX validation: 19/19 PASS
```

| Check | Result |
|-------|--------|
| BTTS No high + low-xG goalscorer withheld | PASS |
| BTTS Yes high + 0-0 score withheld | PASS |
| 1X2 Home + away-win score withheld | PASS |
| 1X2 Home + DC X2 flagged / pick withheld | PASS |
| Under high + aggressive timing withheld | PASS |
| Consistent payload unchanged display | PASS |
| Raw audit preserved | PASS |
| Engine / WDE untouched | PASS |
| Frontend respects `display_allowed` | PASS |
| User vs admin raw audit gating | PASS |

Run locally:

```bash
python scripts/validate_phase42b_global_market_consistency_guard.py
```

---

## Deploy steps (when approved)

### 1. Local build

```powershell
cd base44-d
npm run build
```

### 2. Pack tarball

Include:

- `worldcup_predictor/prediction/market_consistency_guard.py`
- `worldcup_predictor/api/display_helpers.py`
- `scripts/validate_phase42b_global_market_consistency_guard.py`
- `base44-d/dist/` → `_deploy_frontend_dist/`

### 3. Production

```bash
# Upload tarball to /tmp/phase42bfix_deploy.tar.gz
tar xzf /tmp/phase42bfix_deploy.tar.gz -C /opt/worldcup-predictor
rm -rf /var/www/worldcup/frontend/dist/*
cp -a /opt/worldcup-predictor/_deploy_frontend_dist/. /var/www/worldcup/frontend/dist/
systemctl restart worldcup-api
```

### 4. Smoke

```bash
curl -s https://footballpredictor.it.com/api/predict/{fixture_id} -H "Authorization: Bearer $TOKEN" \
  | jq '.consistency_guard.applied, .detailed_markets.goalscorer.display_allowed'
```

Expect `consistency_guard.applied: true` on prediction detail responses.

### 5. Validation on server

```bash
sudo -u www-data env PYTHONPATH=/opt/worldcup-predictor APP_ENV=production bash -lc \
  'cd /opt/worldcup-predictor && set -a && source .env.production && set +a && \
   .venv/bin/python scripts/validate_phase42b_global_market_consistency_guard.py'
```

---

## Rollback plan

1. Restore pre-deploy files from backup:
   - `worldcup_predictor/api/display_helpers.py`
   - Remove `worldcup_predictor/prediction/market_consistency_guard.py` (optional)
   - Restore previous frontend dist
2. `systemctl restart worldcup-api`
3. Guard is read-path only — no migration or cache invalidation required

Cached predictions continue to work; removing the guard simply stops post-processing at API read time.

---

## Architecture note

```
PredictPipeline → build_prediction_output() → cache (raw)
                                              ↓
GET/POST /api/predict → enrich_prediction_payload()
                              ↓
                    apply_market_consistency_guard()  ← Phase 42B-FIX
                              ↓
                    React PredictionDetail (display_allowed aware)
```

This keeps a single global enforcement point for all fixtures without touching model generation.

---

**STOP — awaiting deploy approval.**
