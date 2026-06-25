# PHASE 54H-7 — Expanded Pressure Shadow Backtest Report

**Date:** 2026-06-24  
**Mode:** Expanded Dataset Backtest → Statistical Validation → Feature Importance → Report  
**Dataset:** 153 fixtures, 30,102 pressure rows (server PostgreSQL)  
**Status:** Complete — leakage PASS, validation 13/13 PASS

---

## Executive summary

Expanding from 65 → **153 fixtures** improved sample sizes substantially but **did not establish genuine predictive value** for pressure-augmented models. Pressure **hurts** baseline accuracy on three of four markets when added naïvely (arms B vs A). The large **+22.6%** lift on Goal Minute Bucket remains **minute-proxy dominated** (minute-only arm: **99.3%** accuracy; true pressure lift after controlling minute: **−5.5%**).

### Final recommendation: **`PRESSURE_NO_VALUE`**

Do not promote pressure into EGIE shadow integration at this time. In-play next-goal research may continue only with strict minute controls and larger pre-match rolling-history coverage.

---

## 1. Is Pressure useful?

**No — not as a general EGIE augmentation signal.**

| Evidence | Finding |
|----------|---------|
| Average B-vs-A accuracy delta (4 markets) | **+0.24%** (dominated by spurious goal-minute lift) |
| B-vs-A excluding goal-minute | **−8.6%** average |
| Proxy-controlled minute lift | **−5.5%** |
| Leakage audit | PASS (features are temporally safe) |
| Shadow integration ready | **No** |

Pressure captures **match-state timing** strongly (minute, spikes) but not independent goal-scoring information beyond what minute/score already encode.

---

## 2. Which markets benefit?

| Market | Arm B vs A (Δ accuracy) | Test n | Bootstrap CI (B) | Verdict |
|--------|---------------------------|--------|------------------|---------|
| **Goal Minute Bucket** (in-play) | **+22.6%** | 146 | 91.8%–98.6% | **Spurious** — minute proxy (see §6) |
| Next Goal Team (in-play) | −4.1% | 146 | 52.7%–67.1% | **No benefit** |
| First Goal Team (pre-match) | −8.7% | 23 | 39.1%–78.3% | **Harmful** |
| Goal Range (pre-match) | −13.1% | 23 | 30.4%–65.2% | **Harmful** |

**No market shows statistically reliable improvement from adding pressure to baseline** after proxy controls.

---

## 3. Which markets do not benefit?

All pre-match markets and in-play **Next Goal Team** show **negative** B-vs-A deltas:

- First Goal Team: 69.6% → 60.9% baseline+pressure
- Goal Range: 47.8% → 34.8%
- Next Goal Team: 63.7% → 59.6%

Goal Minute Bucket raw lift is **not a true benefit** — see proxy audit.

---

## 4. Which pressure features matter most?

Pooled importance (arm B, all markets):

| Feature group | Classification | Relative importance |
|---------------|----------------|---------------------|
| `pressure_spike_count` | **STRONG_POSITIVE** | 1.000 |
| `pressure_before_first_goal` | **STRONG_POSITIVE** | 0.678 |
| `pressure_first_30` | WEAK_POSITIVE | 0.485 |
| `pressure_last_5` | WEAK_POSITIVE | 0.463 |
| `pressure_first_15` | WEAK_POSITIVE | 0.392 |
| `pressure_momentum` | WEAK_POSITIVE | 0.265 |
| `pressure_last_10` | NEUTRAL | 0.185 |
| `pressure_swing` | NEUTRAL | 0.157 |
| `pressure_dominance` | NEUTRAL | 0.113 |

**Interpretation:** Spike counts and pre-goal windows dominate — both correlate with **when** goals occur (minute proxy), not **who** scores.

---

## 5. Does pressure beat xG?

On **shared fixtures** with both xG rolling history and pressure (overlap subset):

| Market | Pressure+B | xG+B | Stronger | Δ accuracy |
|--------|------------|------|----------|------------|
| First Goal Team | 63.6% | 54.5% | Pressure | +9.1% |
| Goal Range | 45.5% | 54.5% | xG | −9.1% |
| Team Goals | 48.0% | 44.0% | Pressure | +4.0% |
| Next Goal Team | **62.9%** | 50.0% | **Pressure** | **+12.9%** |

**Head-to-head:** Pressure 3, xG 1 (overlap n small: 22–70 test samples).

**Caveat:** Main backtest on full pressure set shows next-goal **B-vs-A delta −4.1%** vs EGIE baseline proxies. xG comparison uses a **narrow overlap** where xG history exists; results are exploratory, not promotion-grade.

**Overall:** Pressure beats xG on in-play next-goal in overlap, but neither beats the simple EGIE baseline consistently on the full expanded set.

---

## 6. Does pressure survive proxy controls?

**No.** Minute-proxy audit (449 in-play goal events, 146 test):

| Model | Accuracy | Bootstrap 95% CI |
|-------|----------|------------------|
| Minute only (E) | **99.3%** | 97.3%–100% |
| Pressure full (C) | 95.9% | 91.8%–98.6% |
| Pressure w/o minute proxy (F) | 93.8% | 89.0%–97.3% |
| Pressure + minute | 99.3% | — |
| **True lift (F − E)** | **−5.5%** | — |

**Verdict:** `MINUTE_PROXY_RISK_HIGH` (unchanged from 54H-2 despite 2.4× fixture expansion).

Goal-minute bucket lift (+22.6% vs baseline) collapses to **negative** when minute features are controlled.

---

## 7. Is pressure ready for future shadow integration?

**No.**

| Gate | Status |
|------|--------|
| Coverage ≥150 fixtures | ✅ 153 |
| Leakage audit | ✅ PASS |
| Statistical value (B vs A) | ❌ Negative on 3/4 markets |
| Proxy risk | ❌ HIGH |
| Recommendation | `PRESSURE_NO_VALUE` |
| `shadow_integration_ready` | **false** |

Future work would require: (1) exclude goal-minute markets from promotion, (2) improve pre-match rolling coverage (currently **52%**), (3) test pressure on next-goal only with minute held out.

---

## Part A — Dataset rebuild

| Split | Pre-match FGT | Pre-match GR | In-play NG | In-play GMB |
|-------|---------------|--------------|------------|-------------|
| Train | 90 | 97 | 299 | 299 |
| Validation | 26 | 28 | 73 | 73 |
| Test | 27 | 28 | 74 | 74 |
| Total labeled | 143 | 143 | 449 | 449 |
| Pressure coverage % | 52.5% | 52.5% | 99.3% | 99.3% |

**Fixtures:** 153 | **Pre-match rows:** 153 | **In-play rows:** 449  
**Leagues:** CL 65, WC 48, EL 25, Conference 15

Artifacts: `pressure_prematch_dataset.parquet`, `pressure_inplay_dataset.parquet`, `split_report.json`

---

## Part B — Leakage safety

**PASS** — all checks green (`leakage_audit.json`):

- No forbidden keys in pre-match features
- First-fixture teams have no pressure history
- In-play uses pressure strictly before target minute
- No final-score columns in feature set
- No future-fixture temporal leakage

---

## Part C — Backtest arms (summary)

Arms A–F run per market. Key B-vs-A accuracy deltas:

| Market | A baseline | B + pressure | C pressure only | E minute | F no-minute-proxy |
|--------|------------|--------------|-----------------|----------|---------------------|
| First Goal Team | 69.6% | 60.9% | 56.5% | — | — |
| Goal Range | 47.8% | 34.8% | — | — | — |
| Next Goal Team | 63.7% | 59.6% | 57.5% | 53.4% | — |
| Goal Minute Bucket | 73.3% | **95.9%** | 95.9% | **99.3%** | 93.8% |

---

## Part D — Statistical validation

All OK markets report accuracy, log-loss, Brier (binary), ECE, bootstrap 95% CI, and sample sizes. See `expanded_backtest_results.json`.

**Notable:** Pre-match test sets remain small (n≈23) due to rolling-history filter — limits pre-match conclusions.

---

## Validation

**13/13 PASS** (`validation.json`)

- 153 fixtures in store
- Leakage PASS
- No token leaks
- No production / WDE / SaaS / deploy changes
- Threshold status calculated: `PRESSURE_NO_VALUE`

---

## Comparison to Phase 54H-1 (65 fixtures)

| Metric | 54H-1 | 54H-7 (expanded) |
|--------|-------|------------------|
| Fixtures | 65 | **153** |
| In-play rows | ~177 | **449** |
| Next goal B-vs-A | +1.7% | **−4.1%** |
| Goal minute B-vs-A | +27.6% | +22.6% (still proxy) |
| Proxy true lift | −5.2% | **−5.5%** |
| Recommendation | MEDIUM (in-play only) | **NO_VALUE** |

Expansion **increased power** but **reversed** the weak next-goal signal and **confirmed** goal-minute lift is not genuine.

---

## Artifacts

| Path | Description |
|------|-------------|
| `artifacts/phase54h7_expanded_pressure_backtest/expanded_backtest_results.json` | Full backtest |
| `artifacts/phase54h7_expanded_pressure_backtest/minute_proxy_audit.json` | Proxy recheck |
| `artifacts/phase54h7_expanded_pressure_backtest/pressure_vs_xg_compare.json` | xG comparison |
| `artifacts/phase54h7_expanded_pressure_backtest/feature_importance_groups.json` | Feature ranking |
| `artifacts/phase54h7_expanded_pressure_backtest/leakage_audit.json` | Leakage gate |
| `artifacts/phase54h7_expanded_pressure_backtest/validation.json` | Validation |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/phase54h7_expanded_pressure_backtest.py` | Orchestrator |
| `scripts/validate_phase54h7_expanded_pressure_backtest.py` | Validation gate |
| `worldcup_predictor/egie/pressure_backtest/pressure_expanded_runner.py` | Pipeline |
| `worldcup_predictor/egie/pressure_backtest/pressure_vs_xg_compare.py` | xG head-to-head |

---

**Phase 54H-7 complete. No deploy. No live prediction changes. No EGIE scoring changes.**
