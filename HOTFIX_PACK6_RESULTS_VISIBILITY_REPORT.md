# HOTFIX PACK 6 — Results Page Visibility

**Priority:** CRITICAL  
**Date:** 2026-06-26  
**Status:** `RESULTS_VISIBILITY_FIXED`  
**Production:** `91.107.188.229`  
**Validation:** `scripts/validate_hotfix_pack6_results_visibility.py` → **21/21 PASS** (production)

---

## Problem

Yesterday’s evaluated World Cup matches did not appear on `/results` with green/red status despite evaluation rows existing in production.

Users saw empty **Yesterday** and **Last 7 days** tabs while **All evaluated** showed only 4 of 6 known fixtures.

---

## Root causes

| # | Cause | Effect |
|---|--------|--------|
| **RC-1** | Date filter used **kickoff date only** | Fixtures kicked off June 11–13 but evaluated June 20/26 → `yesterday` and `7d` returned **0 rows** |
| **RC-2** | `list_all_worldcup_prediction_evaluations()` excluded **quarantined** rows by default | Fixtures `1489393`, `1539007` invisible despite valid scores |
| **RC-3** | `evaluation_summary_from_row()` returned `None` for quarantined rows | Double-filter even when eval row existed |
| **RC-4** | UI default range was **`7d`** | On production, kickoffs older than 7 days → empty page on first load |

**Not the issue:** API/route missing (Pack 3 already added `/api/results/evaluated` and `/results`).

---

## Production audit (pre-fix)

| Fixture | Eval | Quarantined | Final score | Kickoff | evaluated_at |
|---------|------|-------------|-------------|---------|--------------|
| 1489369 | ✓ | 0 | 2-0 | 2026-06-11 | 2026-06-26 |
| 1489370 | ✓ | 0 | 4-1 | 2026-06-13 | 2026-06-26 |
| 1489393 | ✓ | **1** | 2-1 | 2026-06-20 | 2026-06-20 |
| 1538999 | ✓ | 0 | 2-1 | 2026-06-12 | 2026-06-26 |
| 1539000 | ✓ | 0 | 1-1 | 2026-06-12 | 2026-06-26 |
| 1539007 | ✓ | **1** | 2-1 | 2026-06-20 | 2026-06-20 |

- **Yesterday kickoff (UTC 2026-06-25):** 0 finished fixtures → kickoff-only filter always empty for that day.
- **PredOps:** all 6 have latest snapshots on production.

### API before fix

| Range | total_count | fixture IDs |
|-------|-------------|-------------|
| `all` | 4 | 1489369, 1489370, 1538999, 1539000 |
| `yesterday` | **0** | — |
| `7d` | **0** | — |

---

## Fixes (no WDE / EGIE / model / billing changes)

### 1. Dual-anchor date filtering — `evaluated_results.py`

- `_row_in_range()` matches if **kickoff OR evaluated_at** falls in range.
- Client `utc_offset_minutes` param (`-Date.getTimezoneOffset()`) for local **Yesterday** boundary.

### 2. Quarantined evaluations visible on Results — `evaluated_results.py`, `match_evaluation.py`, `archive_evaluation_join.py`

- `list_all_worldcup_prediction_evaluations(include_quarantined=True)` for Results API.
- `evaluation_summary_from_row(..., include_quarantined=True)` preserves market statuses.
- UI badge: **Data quarantine** when `is_quarantined`.

### 3. Frontend — `PredictionResultsPage.jsx`, `saasApi.js`

- Default tab: **All evaluated** (was `7d`).
- Pass `utcOffsetMinutes` to API.

---

## Post-fix production API

| Range | total_count | Notes |
|-------|-------------|-------|
| `all` | **6** | All known fixtures |
| `7d` | **6** | Via `evaluated_at` anchor |
| `yesterday` | 0* | *No rows with kickoff or evaluated_at on 2026-06-25 UTC; expected |

On **2026-06-27**, fixtures evaluated on 2026-06-26 appear under **Yesterday**.

---

## Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/api/evaluated_results.py` | Dual date range, quarantine include, tz offset |
| `worldcup_predictor/api/match_evaluation.py` | `include_quarantined` on summary |
| `worldcup_predictor/api/archive_evaluation_join.py` | Quarantine-safe market status helpers |
| `worldcup_predictor/api/routes/results.py` | `utc_offset_minutes` query param |
| `base44-d/src/pages/PredictionResultsPage.jsx` | Default `all`, tz offset, quarantine badge |
| `base44-d/src/api/saasApi.js` | `utcOffsetMinutes` param |
| `scripts/validate_hotfix_pack6_results_visibility.py` | Pack 6 validation |

---

## Validation

```bash
python scripts/validate_hotfix_pack6_results_visibility.py
```

Checks:

- ✓ Six known fixtures in `/api/results/evaluated`
- ✓ All DB eval rows visible (including quarantined)
- ✓ `7d` includes rows via `evaluated_at`
- ✓ Yesterday logic (synthetic + API)
- ✓ Final score, pick, market breakdown, colors
- ✓ WDE unchanged

---

## Deploy

- Backup: `/opt/worldcup-predictor/backups/hotfix-pack6-*`
- Frontend rebuilt to `/var/www/worldcup/frontend/dist`
- `worldcup-api` restarted
- Production validation: **21/21 PASS**

### Smoke (localhost on server)

- `GET /api/results/evaluated?range=all` → 6 rows
- `GET /api/results/evaluated?range=7d` → 6 rows
- `/results` SPA route (nginx)
- `/archive`, `/accuracy` unchanged

---

## Unchanged

- WDE scoring
- EGIE engines
- Prediction models / calibration
- Billing / subscriptions

---

## Final status

**`RESULTS_VISIBILITY_FIXED`**
