# PHASE 54H-2 — Pressure Coverage Expansion + Minute-Proxy Risk Audit Report

**Phase:** 54H-2 (shadow / research only)  
**Status:** COMPLETE  
**Validation:** 14/14 PASS  
**Leakage audit:** PASS  
**Proxy audit:** `MINUTE_PROXY_RISK_HIGH`  
**Generated:** 2026-06-24  

---

## Executive summary

Phase 54H-2 attempted to expand pressure coverage beyond 65 fixtures and audit whether the strong in-play goal-minute lift from 54H-1 is real or driven by minute-proxy effects.

| Finding | Result |
|---------|--------|
| Coverage expansion | **Stuck at 65 fixtures** — local cache exhausted; xG cache has no pressure; API backfill added 0 |
| Goal-minute bucket lift | **Not robust** — minute-only model achieves **100% accuracy** |
| True pressure lift (no minute proxy) | **−5.2%** vs minute-only on goal-minute bucket |
| Next goal team | Small +1.7% (B vs A); +1.7% (F vs E) after minute control — within bootstrap noise |
| Final recommendation | **`PRESSURE_PROXY_RISK_HIGH`** |

Do **not** promote in-play goal-minute bucket models. Continue cautious research on next-goal team only after coverage expansion via API with `include=pressure`.

---

## 1. Coverage before/after

| Metric | Before (54H-1) | After (54H-2) | Target |
|--------|----------------|---------------|--------|
| Fixtures with pressure | 65 | 65 | ≥150 (pref 300+) |
| Pressure records | 12,676 | 12,676 | — |
| Cache payloads scanned | 80 (UEFA) | 1,689 (UEFA + xG + duplicate) | — |
| New fixtures imported | — | 0 | — |

### Why expansion failed (documented)

```
Local cache exhausted: 65/80 UEFA payloads contain pressure; 15 lack pressure rows.
Scanned 1,624 additional xG-cache payloads — zero contained pressure (fetched without include=pressure).
API league backfill (CL 2, EL 5, Conference 2286, WC 732): 0 new fixtures processed.
World Cup 732: no pressure cache found.
```

**Artifact:** `artifacts/phase54h2_pressure_expansion_proxy_audit/coverage_expansion.json`

---

## 2. Dataset sizes

| Dataset | Rows | Pressure-available | Notes |
|---------|------|-------------------|-------|
| Pre-match | 65 | 31 (48%) | Rolling history from prior fixtures |
| In-play | 177 | 177 (100%) | One row per scored goal |

### By league

| League | Pre-match | In-play |
|--------|-----------|---------|
| Champions League | 25 | 68 |
| Europa League | 25 | 73 |
| Conference League | 15 | 36 |

### By season

| Season | Pre-match | In-play |
|--------|-----------|---------|
| 23619 | 25 | 68 |
| 23620 | 25 | 73 |
| 23616 | 15 | 36 |

### Label coverage

| Label | Count |
|-------|-------|
| First goal team (pre-match) | 60 |
| Goal range (pre-match) | 60 |
| Next goal team (in-play) | 177 |
| Goal minute bucket (in-play) | 177 |

---

## 3. Backtest results (revalidation, arms A–F)

Temporal split: pre-match 44/21 train/test; in-play 118/58 train/test.

### In-play next goal team

| Arm | Accuracy | Bootstrap CI | Test n |
|-----|----------|--------------|--------|
| A — EGIE baseline | 0.638 | [0.53, 0.76] | 58 |
| B — baseline + pressure | 0.655 | [0.53, 0.76] | 58 |
| C — pressure only | 0.638 | [0.50, 0.76] | 58 |
| D — pressure lite | 0.638 | [0.52, 0.76] | 58 |
| **E — minute only** | 0.535 | [0.38, 0.67] | 58 |
| **F — pressure w/o minute proxy** | 0.552 | [0.41, 0.67] | 58 |

**Δ B vs A:** +1.7% | **Δ F vs E:** +1.7% (not significant vs CI overlap)

### In-play goal minute bucket

| Arm | Accuracy | Bootstrap CI | Test n |
|-----|----------|--------------|--------|
| A — EGIE baseline | 0.672 | [0.53, 0.78] | 58 |
| B — pressure full | 0.948 | [0.90, 1.00] | 58 |
| C — pressure only | 0.948 | [0.90, 1.00] | 58 |
| D — pressure lite | 0.655 | [0.55, 0.78] | 58 |
| **E — minute only** | **1.000** | **[1.00, 1.00]** | 58 |
| F — pressure w/o minute proxy | 0.948 | [0.90, 1.00] | 58 |

**Δ B vs A:** +27.6% — **entirely explained by minute proxy**

### Pre-match (still insufficient)

| Market | Test n | B vs A |
|--------|--------|--------|
| First goal team | 10 | −10.0% |
| Goal range | 10 | 0.0% |

---

## 4. Minute-proxy audit result

**Verdict: `MINUTE_PROXY_RISK_HIGH`**

| Model | Goal-minute accuracy |
|-------|---------------------|
| Minute only (E) | **1.000** |
| Pressure full (C) | 0.948 |
| Pressure w/o minute proxy (F) | 0.948 |
| Pressure + minute | 1.000 |
| EGIE baseline | 0.672 |

### Key comparisons

| Metric | Value |
|--------|-------|
| Minute-only accuracy | 100.0% |
| Pressure-only (no minute-proxy features) | 94.8% |
| True pressure lift after controlling minute | **−5.2%** |
| Minute explains most of pressure-full lift | **Yes** |

**Interpretation:** At the instant before a goal, `current_minute` trivially determines the goal-minute bucket (minute 8 → `0-15`, minute 25 → `16-30`). Pressure window features (`first_30`, `last_5`, spike counts) encode elapsed match time and replicate this signal. This is **not** independent predictive value.

**Artifact:** `minute_proxy_audit.json`

---

## 5. True pressure lift after controlling minute

| Market | Lift metric | Value | Robust? |
|--------|-------------|-------|---------|
| Goal minute bucket | F vs E (accuracy) | −5.2% | **No** — minute dominates |
| Goal minute bucket | B vs A | +27.6% | **No** — proxy artifact |
| Next goal team | F vs E | +1.7% | **Uncertain** — CI overlap |
| Next goal team | B vs A | +1.7% | **Uncertain** — small n |

For next goal team, minute-only (53.5%) underperforms pressure-without-minute (55.2%), suggesting a marginal non-proxy signal — but bootstrap CIs overlap heavily.

---

## 6. Feature importance (proxy-aware)

| Feature | Bucket | Notes |
|---------|--------|-------|
| `pressure_spike_count_away` | robust_signal | High importance but correlates with match phase |
| `pressure_momentum` | robust_signal | Moderate; worth monitoring |
| `pressure_swing` | robust_signal | Moderate |
| `pressure_before_first_goal_away` | **minute_proxy** | Time-anchored window |
| `pressure_first_15_home` | **minute_proxy** | Fixed kickoff window |
| `pressure_last_5_*` | **minute_proxy** | Anchored to current minute |
| `pressure_dominance` | unstable / harmful | Low incremental value |

---

## 7. Safety compliance

| Rule | Status |
|------|--------|
| No production prediction changes | ✅ |
| No WDE / SaaS / EGIE scoring changes | ✅ |
| No deploy / live integration | ✅ |
| No token leaks | ✅ |
| Leakage audit PASS | ✅ |

---

## 8. Final recommendation

### `PRESSURE_PROXY_RISK_HIGH`

1. **Do not promote** in-play goal-minute bucket models — lift is minute-proxy artifact.
2. **Do not claim** 54H-1 +27.6% goal-minute improvement as pressure value.
3. **Coverage blocked** at 65 fixtures until Sportmonks API backfill with `include=pressure` on fresh fixture IDs (budget ~85+ calls minimum).
4. **Optional continued research:** in-play next goal team with pressure-without-minute features — only after reaching ≥150 fixtures and confirming F vs E lift holds outside bootstrap noise.

### Next steps (if approved later)

1. Dedicated pressure API backfill script targeting finished UEFA fixtures not in store (max-calls budget).
2. Re-fetch xG fixture IDs with `include=pressure` into `data/feature_store/sportmonks_pressure/raw`.
3. Re-run 54H-2 when coverage ≥150.

---

## Module map

| Component | Path |
|-----------|------|
| Coverage expansion | `SportmonksPressureFeatureStore.backfill_expansion()` |
| Minute proxy audit | `worldcup_predictor/egie/pressure_backtest/minute_proxy_audit.py` |
| Revalidation runner | `worldcup_predictor/egie/pressure_backtest/pressure_revalidation_runner.py` |
| CLI | `scripts/phase54h2_pressure_expansion_proxy_audit.py` |
| Validation | `scripts/validate_phase54h2_pressure_expansion_proxy_audit.py` |

**Artifacts:** `artifacts/phase54h2_pressure_expansion_proxy_audit/`

---

**STOP** — Phase 54H-2 complete. No deploy. No live prediction changes.
