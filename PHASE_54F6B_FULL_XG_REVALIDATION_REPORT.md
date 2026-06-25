# PHASE 54F-6B — Full xG Revalidation Report (1,004 Fixtures)

**Date:** 2026-06-24  
**Mode:** Backtest Revalidation → Statistical Analysis → Feature Importance → Report  
**Status:** COMPLETE (backtest only — no production, WDE, SaaS, or deploy changes)

**Dataset:** `artifacts/phase54f6_expanded_dataset/expanded_egie_dataset.parquet`  
**Artifacts:** `artifacts/phase54f6b_full_xg_revalidation/full_revalidation.json`

---

## Executive Summary

This is the **strongest xG evidence to date** — **1,004 usable fixtures**, **201 held-out test fixtures per market**, bootstrap confidence intervals, and market-specific analysis.

| Finding | Result |
|---------|--------|
| Sample size sufficient? | **YES** (1,004 usable, 192–201 test) |
| Aggregate xG value tier | **`LOW_VALUE`** |
| Final recommendation | **`XG_LOW_VALUE`** |
| Phase 54G ready? | **NO** |
| Statistically significant accuracy gains? | **None** (all 95% CIs cross zero) |

**Bottom line:** xG is **not useless**, but it is **not ready for blanket EGIE production**. Goal Range (+5.7%) and Team Goals (+2.5%) show promise; First Goal Team (−4.7%) is harmed by the full xG feature stack.

---

## Part A — Dataset Verification

| Metric | Value |
|--------|-------|
| Total usable fixtures | **1,004** |
| Train (60%) | 602 |
| Validation (20%) | 201 |
| Test (20%) | 201 |
| Rolling xG 3/5/10 | 1,004 each (100%) |
| First goal labeled | 950 |
| Goal range labeled | 950 |
| Team goals labeled | 1,004 |

### By league

| League | Total | Train | Val | Test |
|--------|-------|-------|-----|------|
| World Cup | 23 | 0 | 0 | 23 |
| Champions League | 399 | 272 | 64 | 63 |
| Europa League | 390 | 255 | 65 | 70 |
| Conference League | 192 | 75 | 72 | 45 |

Split: temporal 60/20/20 on `kickoff_utc`. Fit on train+validation (803), evaluate on test.

---

## Part B — Full A/B Revalidation

**Arm A:** EGIE baseline (`home_goal_rate_proxy`, `away_goal_rate_proxy`, history samples)  
**Arm B:** Baseline + 20 Sportmonks rolling xG features  
**Model:** GradientBoostingClassifier, temporal holdout

### Summary table (test set)

| Market | n | Arm A Acc | Arm B Acc | Δ Acc | Δ LogLoss | Δ Brier | Δ ECE |
|--------|---|-----------|-----------|-------|-----------|---------|-------|
| First Goal Team | 192 | 58.3% | 53.7% | **−4.7%** | +0.048 | +0.018 | +0.033 |
| Goal Range | 192 | 33.9% | 39.6% | **+5.7%** | +0.062 | — | — |
| Team Goals | 201 | 51.2% | 53.7% | **+2.5%** | **−0.036** | **−0.013** | **−0.050** |

---

## Part C — Confidence Analysis

| Market | Calibration gain (↓ECE) | Confidence Δ | Sharpness Δ | Reliability |
|--------|---------------------------|--------------|-------------|-------------|
| First Goal Team | **−0.033** (worse) | +0.027 | +0.024 | Worse |
| Goal Range | n/a (multiclass) | +0.012 | +0.000 | Unchanged |
| Team Goals | **+0.050** (better) | −0.009 | +0.002 | **Improved** |

xG **improves probability reliability for Team Goals** (lower ECE, lower Brier, lower logloss) but **worsens calibration for First Goal Team**.

---

## Part D — Feature Importance (Top 14 xG features)

| Rank | Feature | Share % | Classification |
|------|---------|---------|----------------|
| 1 | `away_recent_xga` | 14.7% | Strong Positive |
| 2 | `home_recent_xga` | 13.5% | Strong Positive |
| 3 | `rolling_xg_10_away` | 10.9% | Strong Positive |
| 4 | `rolling_xg_3_away` | 9.7% | Strong Positive |
| 5 | `xg_momentum_difference` | 9.2% | Strong Positive |
| 6 | `rolling_xg_10_home` | 8.7% | Strong Positive |
| 7 | `rolling_xg_3_home` | 7.7% | Strong Positive |
| 8 | `defensive_weakness_difference` | 7.3% | Strong Positive |
| 9 | `attack_strength_difference` | 4.9% | Weak Positive |
| 10 | `xg_difference` | 3.2% | Weak Positive |
| 11–14 | `rolling_xg_5_*`, `home/away_recent_xg` | 2.3–2.9% | Weak Positive |

### Features to consider removing

| Feature | Reason |
|---------|--------|
| `home_recent_xg`, `away_recent_xg` | Weak importance; superseded by xGA and rolling windows |
| `rolling_xg_5_home`, `rolling_xg_5_away` | Redundant with rolling_xg_3/10; lowest rolling-window signal |
| Full xG stack for **First Goal Team** | Net −4.7% accuracy; use baseline-only for this market |

**Keep:** xGA pair, rolling_xg_3/10, momentum, defensive_weakness_difference.

---

## Part E — Statistical Significance (Bootstrap n=1000)

| Market | Δ Acc mean | 95% CI | P(improve) | Significant? |
|--------|------------|--------|------------|--------------|
| First Goal Team | −4.8% | [−13.0%, +4.2%] | 11.4% | **No** (likely noise) |
| Goal Range | +5.8% | [−2.1%, +14.1%] | 91.4% | **No** (CI crosses 0) |
| Team Goals | +2.7% | [−4.5%, +9.5%] | 74.4% | **No** (CI crosses 0) |

**Interpretation:** Directional signals exist (especially Goal Range p=91% improve), but **no market meets strict 95% significance** on accuracy delta. Team Goals shows consistent secondary metrics improvement (logloss, Brier, ECE).

---

## Part F — Market-Specific Results

### First Goal Team
- **Baseline:** 58.3% acc, ECE 0.099
- **+ xG:** 53.7% acc, ECE 0.132
- **Recommendation:** `NO_VALUE` — **do not add xG**

### Goal Range
- **Baseline:** 33.9% acc
- **+ xG:** 39.6% acc (+16.9% relative)
- **Recommendation:** `MEDIUM_VALUE` — promising but not statistically confirmed

### Team Goals (Over 2.5)
- **Baseline:** 51.2% acc, Brier 0.285, ECE 0.156
- **+ xG:** 53.7% acc, Brier 0.272, ECE 0.106
- **Recommendation:** `LOW_VALUE` — best calibrated market for xG

---

## Part G — Final Decision

| Tier | Assignment |
|------|------------|
| VERY_HIGH_VALUE | No |
| HIGH_VALUE | No |
| MEDIUM_VALUE | No (aggregate) |
| **LOW_VALUE** | **Yes (aggregate avg Δ +1.2%)** |
| NO_VALUE | No |

**Aggregate accuracy delta:** (+5.7% − 4.7% + 2.5%) / 3 ≈ **+1.2%**

---

## Part H — Answers to Required Questions

### 1. Is xG useful for EGIE?
**Partially.** Useful for **Team Goals** and possibly **Goal Range**; **harmful for First Goal Team** with current feature bundle.

### 2. Which markets benefit?
- **Team Goals** (+2.5% acc, better logloss/Brier/ECE)
- **Goal Range** (+5.7% acc, 91% bootstrap p-improve)

### 3. Which markets do not benefit?
- **First Goal Team** (−4.7% acc, worse calibration)

### 4. Which xG features matter most?
`away_recent_xga`, `home_recent_xga`, `rolling_xg_10_away`, `rolling_xg_3_away`, `xg_momentum_difference`

### 5. Which features should be removed?
Raw `home_recent_xg` / `away_recent_xg`, redundant `rolling_xg_5_*`, entire xG arm for First Goal Team.

### 6. Does xG improve confidence quality?
**Yes for Team Goals** (ECE −0.05). **No for First Goal Team** (ECE +0.03).

### 7. Should xG enter production in the future?
**Not yet as a universal layer.** Consider a **Team Goals–only xG arm** after another holdout cycle.

### 8. Is the sample size now sufficient?
**YES.** 1,004 usable, 192–201 test per market — adequately powered for directional conclusions; strict significance still elusive for accuracy.

### 9. Should Phase 54G begin?
**NO.** `READY_FOR_54G` is **not** recommended.

---

## Final Recommendation: `XG_LOW_VALUE`

| Option | Status |
|--------|--------|
| READY_FOR_54G | **NO** |
| CONTINUE_XG_RESEARCH | **YES** — market-specific arms, feature pruning |
| **XG_LOW_VALUE** | **SELECTED** — modest aggregate signal, not production-ready |
| XG_NO_VALUE | **NO** — clear positive signal in 2/3 markets |

### Next actions
1. Ship **Team Goals xG arm** as shadow-only with trimmed features (xGA + momentum + rolling_xg_10).
2. Keep **First Goal Team** on baseline-only.
3. Re-test **Goal Range** with xG-only subset after feature pruning.
4. Do not start Phase 54G until xG value is confirmed on a forward holdout.

---

**Validation:** `scripts/validate_phase54f6b_full_xg_revalidation.py`  
**STOP** — Phase 54F-6B complete. No deploy. No live prediction changes.
