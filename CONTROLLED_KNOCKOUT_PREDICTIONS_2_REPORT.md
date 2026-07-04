# CONTROLLED-KNOCKOUT-PREDICTIONS-2 — Report

**Mode:** Discover → Odds Audit → Controlled Refresh → Prediction Dry-run → Controlled Prediction → Store Snapshots → Owner List  
**Environment:** Hetzner `/opt/worldcup-predictor`, `APP_ENV=production`  
**Date:** 2026-07-04

---

## Executive summary

Two of three controlled knockout predictions stored successfully using the same frozen-snapshot workflow as Colombia vs Ghana. **Canada vs Morocco** and **Paraguay vs France** have fresh-odds WDE + ECSE snapshots. **Brazil vs Norway** blocked on missing odds and a pipeline import error. Colombia frozen evidence unchanged (validation 30/30).

**Final recommendation:** `PARTIAL_PREDICTION_SUCCESS`

---

## Part A — Discovery

| Match | fixture_id | Kickoff Vienna | Round | Pre-run odds |
|-------|-----------:|----------------|-------|--------------|
| Canada vs Morocco | **1567824** | 2026-07-04 19:00 CEST | Round of 16 | STALE 7.67h |
| Paraguay vs France | **1569870** | 2026-07-04 23:00 CEST | Round of 16 | STALE 7.67h |
| Brazil vs Norway | **1568100** | 2026-07-05 22:00 CEST | Round of 16 | ODDS_MISSING |

See `CONTROLLED_KNOCKOUT_PREDICTIONS_2_DISCOVERY.md`.

---

## Part B — Colombia frozen verification

| Check | Result |
|-------|--------|
| Actual 1-0 | Confirmed |
| WDE 1X2/BTTS/O/U | HIT / HIT / HIT |
| ECSE Top1 MISS, Top3 HIT rank 2, Top5 HIT | Confirmed |
| Payload hash | `07b841fc1025af28` unchanged |
| Validation | 30/30 passed |

No mutation.

---

## Part C — Odds workflow

### Canada (1567824)

| Step | Result |
|------|--------|
| Audit before | STALE_ODDS · would_refresh=1 |
| Refresh dry-run | would_refresh=1 |
| Refresh real | **refreshed=3** markets · provider calls bounded |
| Audit after | FRESH_ODDS · would_refresh=0 |
| Markets | 1X2 · BTTS · O/U · Correct Score available |

### Paraguay (1569870)

| Step | Result |
|------|--------|
| Audit before | STALE_ODDS (shared batch already refreshed at 08:36:41 UTC) |
| Refresh dry-run | would_refresh=0 (already fresh from Canada batch) |
| Refresh real | Skipped (one attempt rule) |
| Audit after | FRESH_ODDS |
| Markets | 1X2 · BTTS · O/U · Correct Score available |

### Brazil (1568100)

| Step | Result |
|------|--------|
| Audit before | ODDS_MISSING |
| Refresh | **Failed** — `ModuleNotFoundError: worldcup_predictor.owner_daily.discovery` |
| Audit after | ODDS_MISSING |
| Markets | None |

---

## Part D — Prediction dry-runs

| fixture_id | Targeted only | WDE would create | ECSE would create | Provider bounded |
|-----------:|---------------|------------------|-------------------|------------------|
| 1567824 | ✅ | ✅ | ✅ | ✅ |
| 1569870 | ✅ | ✅ | ✅ | ✅ |
| 1568100 | ✅ | WDE only (dry) | ❌ missing_odds | ✅ |

---

## Part E — Controlled real predictions

| Match | WDE stored | ECSE stored | Result |
|-------|------------|-------------|--------|
| Canada vs Morocco | ✅ | ✅ snapshot id=2 | Success |
| Paraguay vs France | ✅ | ✅ snapshot id=3 | Success |
| Brazil vs Norway | ❌ | ❌ | Failed — missing odds + pipeline error |

---

## Part F — Stored outputs

### Canada vs Morocco (1567824)

| Field | Value |
|-------|-------|
| WDE 1X2 | Away (Morocco) · 60.4% |
| BTTS | Yes |
| O/U | Under 2.5 |
| ECSE Top1 | 0-1 |
| ECSE Top3 | 0-1 · 0-2 · 1-1 |
| ECSE Top5 | 0-1 · 0-2 · 1-1 · 1-2 · 0-0 |
| Odds | FRESH_ODDS · 2026-07-04T08:36:41+00:00 |
| Engine | WDE 34b-v1 · ECSE ECSE-LIVE-1\|ECSE-1C-v1\|ECSE-1D-B-v1 |

### Paraguay vs France (1569870)

| Field | Value |
|-------|-------|
| WDE 1X2 | Away (France) · 54.8% |
| BTTS | No |
| O/U | Over 2.5 |
| ECSE Top1 | 0-2 |
| ECSE Top3 | 0-2 · 0-3 · 0-4 |
| ECSE Top5 | 0-2 · 0-3 · 0-4 · 0-1 · 0-5 |
| Odds | FRESH_ODDS · 2026-07-04T08:36:41+00:00 |
| Engine | WDE 34b-v1 · ECSE ECSE-LIVE-1\|ECSE-1C-v1\|ECSE-1D-B-v1 |

### Brazil vs Norway (1568100)

No stored prediction.

---

## Part G — Cross-market consistency

| Fixture | WDE↔ECSE direction | BTTS | O/U | Draw diversification | Notes |
|---------|-------------------|------|-----|---------------------|-------|
| Canada | ✅ Away aligned | ✅ Yes + 1-1/1-2 | ✅ Under + Top3 ≤2 goals | ✅ 1-1 in Top3 | Clean-sheet away scores normal with mixed BTTS |
| Paraguay | ✅ Away aligned | ✅ No + zero home goals | ✅ Over + Top3 ≥2 goals | Limited (heavy favorite) | No CROSS_MARKET_VARIANCE_CANDIDATE |
| Brazil | N/A | — | — | — | Not predicted |

---

## Part H — Owner list

See `CONTROLLED_KNOCKOUT_PREDICTIONS_2_OWNER_LIST.md`.

---

## Part I — Production counters

| Metric | Before | After |
|--------|-------:|------:|
| ECSE snapshots total | 1 | **3** |
| ECSE evaluated | 1 | 1 |
| ECSE pending | 0 | **2** |
| WDE stored | 49 | **51** |
| WDE evaluated | 35 | 35 |
| WDE pending | 14 | 16 |

Directional ECSE: 1 → 3 (+2 new pending snapshots).

---

## Part J — Validation

**Script:** `scripts/validate_controlled_knockout_predictions_2.py`

Run on Hetzner — **23/23 checks passed** (`all_passed: true`).

---

## Part K — Constraints honored

- Colombia not regenerated or re-evaluated
- No WDE/ECSE formula changes
- No S5 or selector promotion
- Timers disabled
- Bounded provider calls per fixture
- Separate controlled runs per fixture (no broad daily mode)

---

## Final recommendation

**`PARTIAL_PREDICTION_SUCCESS`**

Two controlled WDE+ECSE predictions created with fresh odds. Brazil vs Norway requires odds provider data and/or `owner_daily.discovery` module fix before retry. Do not evaluate pending fixtures until officially finished.

---

## Artifacts

| File | Purpose |
|------|---------|
| `CONTROLLED_KNOCKOUT_PREDICTIONS_2_DISCOVERY.md` | Part A |
| `CONTROLLED_KNOCKOUT_PREDICTIONS_2_OWNER_LIST.md` | Part H |
| `CONTROLLED_KNOCKOUT_PREDICTIONS_2_REPORT.md` | This report |
| `scripts/discover_controlled_knockout_predictions_2.py` | Discovery |
| `scripts/run_controlled_knockout_predictions_2.py` | Workflow orchestrator |
| `scripts/inspect_controlled_knockout_predictions_2.py` | Inspection |
| `scripts/validate_controlled_knockout_predictions_2.py` | Validation |
| `artifacts/controlled_knockout_predictions_2/workflow_results.json` | Full workflow log |
