# BUGFIX — Goal Timing Internal Consistency Report

**Date:** 2026-06-21  
**Issue:** Prediction Detail showed `Minute Range = 16-30` with `Expected Minute = 38`  
**Status:** **FIXED & VALIDATED (NOT DEPLOYED)**

---

## Executive summary

Root cause is a **backend payload assembly bug**, not a frontend mapping issue. `build_detailed_markets()` mixes two independent sources for first-goal timing. The Market Consistency Guard now enforces **TIMING_RANGE_CONSISTENCY**: when `expected_minute` falls outside `minute_range`, the display range is realigned to the band containing the expected minute (e.g. `16-30` + `38` → `31-45` + `38`).

---

## Audit findings

### Payload path (`detailed_markets.first_goal`)

| Field | Source | Example |
|-------|--------|---------|
| `minute_range` | `prediction.first_goal.minute_range` first, else `snap.first_goal_time.minute_band` | `"16-30"` from `scoring_engine` when `total_goals >= 2.5` |
| `expected_minute` | Always `snap.first_goal_time.expected_minute` from extended markets | `38` = midpoint of band `"31-45"` |

**File:** `worldcup_predictor/api/prediction_output.py` (lines ~182–234)

```python
minute_range = prediction.first_goal.minute_range or (
    snap.first_goal_time.minute_band if snap else None
)
...
"expected_minute": snap.first_goal_time.expected_minute if snap else None,
```

### Extended markets snap

**File:** `worldcup_predictor/prediction/extended_markets.py`

`_first_goal_time()` sets `expected_minute` from `_BAND_MIDPOINT`:

| Band | Midpoint |
|------|----------|
| 16-30 | 23 |
| **31-45** | **38** |
| 46-60 | 53 |

When the engine sets `prediction.first_goal.minute_range = "16-30"` but extended markets compute timing from a different band (e.g. fg_v2 or internal xG path → `31-45`), the API exposes **mismatched fields**.

### Frontend

**File:** `base44-d/src/pages/PredictionDetail.jsx`

Renders both values as returned by the API — **no frontend bug**.

### Consistency guard (before fix)

Phase 42B-FIX guard checked Under 2.5 vs early timing but **did not validate internal range/minute consistency**.

---

## Root cause

**Split-source payload assembly** in `build_detailed_markets()`:

- Display band prefers engine heuristic (`16-30` / `31-45` from goal total)
- Expected minute always from extended-markets Poisson/xG band midpoint

These can diverge on the same fixture → user sees minute 38 outside range 16-30.

---

## Fix implemented

### New module

`worldcup_predictor/prediction/market_consistency_timing.py`

- Band parsing (`0-15`, `16-30`, … `76-90+`)
- `expected_minute_in_band(minute, band)`
- `band_for_expected_minute(minute)`

### Guard rule: `TIMING_RANGE_CONSISTENCY`

**File:** `worldcup_predictor/prediction/market_consistency_guard.py`

Applied **before** Under 2.5 timing rules:

1. If `expected_minute` ∈ `minute_range` → unchanged (`ok`)
2. If outside → **recompute `minute_range`** from expected minute (`warning`, `timing_range_aligned: true`)
3. If unparseable / unalignable → **withhold** first-goal timing block

Raw audit still preserves pre-guard values in `consistency_guard.raw_markets_audit`.

**Not changed:** prediction engine, WDE, frontend (guard output is already consumed correctly).

---

## Validation results

### Bugfix suite

```bash
python scripts/validate_bugfix_timing_range_consistency.py
```

```
Bugfix timing range consistency: 9/9 PASS
```

| Case | Input | Result |
|------|-------|--------|
| Mismatch detect | 16-30 + 38 | Detected as out-of-range |
| Mismatch fix | 16-30 + 38 | Aligned to **31-45** + 38 |
| Valid | 31-45 + 38 | Unchanged |
| Valid | 0-15 + 12 | Unchanged |

### Regression

```
Phase 42B-FIX validation: 19/19 PASS
Phase 42B-FIX config hardening: 16/16 PASS
```

---

## Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/prediction/market_consistency_timing.py` | **Added** — band helpers |
| `worldcup_predictor/prediction/market_consistency_guard.py` | **Updated** — `TIMING_RANGE_CONSISTENCY` rule |
| `worldcup_predictor/prediction/market_consistency_config.py` | **Updated** — `rules_version` → `42b-fix-timing-v1` |
| `scripts/validate_bugfix_timing_range_consistency.py` | **Added** — 9-check validation |

---

## Before / after (user-visible)

**Before:**

```
Minute Range:    16-30
Expected Minute: 38'
```

**After (guard applied):**

```
Minute Range:    31-45
Expected Minute: 38'
```

(Consistency warning recorded in `consistency_guard`; display remains allowed after alignment.)

---

## Deploy steps (when approved)

Deploy with Phase 42B-FIX bundle:

1. `market_consistency_timing.py`
2. `market_consistency_guard.py`
3. `market_consistency_config.py`
4. `scripts/validate_bugfix_timing_range_consistency.py`

```bash
systemctl restart worldcup-api
python scripts/validate_bugfix_timing_range_consistency.py
python scripts/validate_phase42b_global_market_consistency_guard.py
```

---

## Rollback

Restore previous `market_consistency_guard.py` and remove `market_consistency_timing.py`. Restart API. No migration required.

---

## Future improvement (optional, not in scope)

Align sources at build time in `prediction_output.py` so cached payloads are consistent before guard — would reduce reliance on post-processing for this specific bug.

---

**STOP — awaiting deploy approval.**
