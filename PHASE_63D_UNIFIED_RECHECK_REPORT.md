# Phase 63D — Unified Engine Recheck Report

**Date:** 2026-06-26  
**Script:** `scripts/validate_phase61b_production_egie_unified.py`  
**Post-data:** Phase 63C EGIE completion run  
**Public flags:** **NOT enabled** (owner approval required)

---

## Executive summary

| Item | Value |
|------|-------|
| **Recommendation** | **`ADMIN_PREVIEW_ONLY`** |
| Unified engine on server | Available |
| `UNIFIED_ENGINE_ENABLED` | `false` |
| `UNIFIED_ENGINE_PUBLIC` | `false` |
| `UNIFIED_ENGINE_ADMIN_PREVIEW` | `true` |
| Phase 61B decision label | `BLOCKED` (public rollout) |

---

## Engine comparison (56 WC 2026 stored predictions)

### Coverage

| Market | Classic cov | EGIE cov | Unified cov |
|--------|-------------|----------|-------------|
| 1X2 | 100% | 0% | 73.2% |
| BTTS | 78.6% | 0% | 78.6% |
| Over/Under | 78.6% | 0% | 96.4% |
| First goal team | 0% | 0% | 0% |
| Goal range | 0% | 0% | 0% |
| Goal minute | 0% | 0% | 0% |

### Accuracy (settled sample, n=56)

| Market | Classic | EGIE | Unified |
|--------|---------|------|---------|
| 1X2 | 28.6% | N/A | 28.6% |
| BTTS | N/A | N/A | N/A |
| Over/Under | N/A | N/A | N/A |

*Small sample — accuracy not statistically stable.*

### Provider hits (fixtures with data)

```json
{
  "odds": 50,
  "xg": 0,
  "lineups": 0,
  "classic_cache": 56,
  "egie_cache": 0
}
```

Note: EGIE cache hit counts reflect PostgreSQL goal_timing connection state during root-level validation run. SQLite EGIE artifacts exist (308 raw rows) but PG goal_timing features remain sparse.

### Tier distribution (Unified)

| Tier | Count |
|------|-------|
| B | 9 |
| C | 43 |
| D | 4 |

---

## Hybrid contribution

| Market | Dominant source |
|--------|-----------------|
| 1X2 | Classic (WDE production cache) |
| BTTS | Classic |
| Over/Under | Classic + hybrid routing |
| First goal / timing | Hybrid layer when EGIE data present (limited by 9.2% goal-event coverage) |

---

## Calibration / ROI

- **Calibration:** Not re-run in this phase — sample too small (56 fixtures, 36 evaluations)
- **ROI:** Insufficient settled best-bet history for unified-vs-classic ROI split
- **EGIE timing markets:** Blocked by goal-event coverage (<10%)

---

## Recommendation matrix

| Option | Fit |
|--------|-----|
| `READY_FOR_PUBLIC_ROLLOUT` | **No** — EGIE coverage near zero on live fixtures; accuracy unproven |
| `ADMIN_PREVIEW_ONLY` | **Yes** — compare mode safe for super_admin; flags already set |
| `NEED_MORE_DATA` | Partial — need goal events + xG on live WC fixtures |
| `PROVIDER_LIMITED` | **Yes** — Sportmonks/API-Football caps bind EGIE expansion |

### Final recommendation: **`ADMIN_PREVIEW_ONLY`**

Keep deployment flags:

```
UNIFIED_ENGINE_ENABLED=false
UNIFIED_ENGINE_PUBLIC=false
UNIFIED_ENGINE_ADMIN_PREVIEW=true
UNIFIED_ENGINE_COMPARE_MODE=true
```

**Do not enable public Unified Engine without explicit owner approval.**

---

**Stopped — no public flag changes made.**
