# PHASE 54F-7 — Market-Specific xG Optimization Report

**Date:** 2026-06-24  
**Mode:** Research → Feature Selection → Market-Specific Validation → Report  
**Status:** COMPLETE (backtest only — no production, WDE, SaaS, or deploy changes)

**Dataset:** `artifacts/phase54f6_expanded_dataset/expanded_egie_dataset.parquet` (1,004 usable fixtures)  
**Artifacts:** `artifacts/phase54f7_market_specific_xg/market_specific_optimization.json`

---

## Executive Summary

Phase 54F-7 confirms that **xG is not a universal EGIE feature**. When evaluated in **isolated market tracks** with multiple feature arms, the evidence supports **market-specific policies**:

| Market | Best Arm | Δ Accuracy vs Baseline | Production Readiness |
|--------|----------|--------------------------|----------------------|
| First Goal Team | Baseline (no xG) | Full xG: **−4.7%** | **NO_VALUE** |
| Goal Range | `top10_xg` | **+6.3%** | **RESEARCH_ONLY** |
| Team Goals | `top5_xg` | **+3.0%** | **RESEARCH_ONLY** |

**Final recommendation:** **`CONTINUE_XG_RESEARCH`**

xG should **not** enter blanket production. It shows directional value in Goal Range and Team Goals when feature sets are tuned per market, but **no market meets strict production-ready significance thresholds**.

---

## Part A — Market Isolation

Three independent tracks were run with no shared conclusions:

| Track | Market | Test n | Split |
|-------|--------|--------|-------|
| A | First Goal Team | 192 | 60/20/20 temporal |
| B | Goal Range | 192 | 60/20/20 temporal |
| C | Team Goals (O/U 2.5) | 201 | 60/20/20 temporal |

Fit pool: train + validation (758 for FG/GR, 803 for TG). Evaluate on held-out test only.

---

## Part B — First Goal Team: Remove xG

### Baseline vs Baseline + Full xG

| Metric | Baseline | + Full xG | Δ |
|--------|----------|-----------|---|
| Accuracy | 58.3% | 53.7% | **−4.7%** |
| LogLoss | 0.696 | 0.744 | +0.048 |
| Brier | 0.250 | 0.267 | +0.018 |
| Calibration ECE | 0.099 | 0.132 | +0.033 |
| Confidence mean | 0.653 | 0.680 | +0.027 |

### Bootstrap (n=1000)

| Δ Acc mean | 95% CI | P(improve) | Significant? |
|------------|--------|------------|--------------|
| −4.8% | [−13.0%, +4.2%] | 11.4% | No |

xG **consistently hurts** First Goal Team (accuracy delta < −2%, P(improve) < 25%).

### Feature Contribution Audit

| Category | Features |
|----------|----------|
| **Harmful** (high importance, net harm) | `home_recent_xga`, `away_recent_xga`, `xg_momentum_difference`, `rolling_xg_3_away`, `rolling_xg_10_home`, `rolling_xg_10_away` |
| **Unstable** | `xg_difference`, `attack_strength_difference`, `defensive_weakness_difference`, `rolling_xg_3_home`, `rolling_xg_5_away` |
| **Neutral** | `home_recent_xg`, `away_recent_xg`, `rolling_xg_5_home`, all `rolling_xga_*` |

### Policy

**`NO_XG_FOR_FIRST_GOAL_TEAM`** — Do not force xG into this market.

---

## Part C — Goal Range Optimization

### Arm Comparison (test n=192)

| Arm | Accuracy | Δ Acc | Δ LogLoss | Notes |
|-----|----------|-------|-----------|-------|
| Baseline | 33.9% | — | — | |
| **top10_xg** | **40.1%** | **+6.3%** | +0.064 | **Best arm** |
| full_xg | 39.6% | +5.7% | +0.062 | Strong secondary |
| xg_only | 34.9% | +1.1% | +0.070 | xG alone weak |
| top5_xg | 33.9% | 0.0% | +0.056 | No accuracy gain |
| xg_lite | 33.3% | −0.5% | +0.060 | Underperforms full |

### Bootstrap — Best Arm (`top10_xg`)

| Δ Acc mean | 95% CI | P(improve) | Significant? |
|------------|--------|------------|--------------|
| +6.3% | [−1.6%, +14.6%] | 93.4% | No (CI crosses 0) |

### Most Useful xG Features (Goal Range)

Ranked by model importance in `full_xg` arm:

1. `away_recent_xga` (13.7%)
2. `home_recent_xga` (10.4%)
3. `rolling_xg_3_away` (9.5%)
4. `xg_momentum_difference` (9.3%)
5. `rolling_xg_10_away` (8.9%)

**Finding:** Top-10 xG subset outperforms both full stack and XG_LITE for Goal Range. The full 20-feature stack adds noise; a curated top-10 set is optimal in this backtest.

---

## Part D — Team Goals Optimization

### Arm Comparison (test n=201)

| Arm | Accuracy | Δ Acc | Δ LogLoss | Δ Brier | Δ ECE |
|-----|----------|-------|-----------|---------|-------|
| Baseline | 51.2% | — | — | — | 0.156 |
| **top5_xg** | **54.2%** | **+3.0%** | −0.032 | −0.012 | −0.038 |
| full_xg | 53.7% | +2.5% | **−0.036** | **−0.013** | **−0.050** |
| xg_only | 52.2% | +1.0% | −0.037 | −0.012 | −0.042 |
| xg_lite | 51.2% | 0.0% | −0.020 | −0.006 | −0.013 |
| top10_xg | 51.2% | 0.0% | −0.033 | −0.011 | −0.024 |

### Bootstrap — Best Arm (`top5_xg`)

| Δ Acc mean | 95% CI | P(improve) | Significant? |
|------------|--------|------------|--------------|
| +3.0% | [−4.0%, +10.0%] | 77.6% | No |

### Team Goals Sub-questions

| Question | Answer |
|----------|--------|
| Does xG improve O/U 2.5 accuracy? | **Yes, directionally** (+2.5% to +3.0% with top5/full) |
| Team goal expectation (logloss/Brier)? | **Yes** — full_xg improves logloss (−0.036), Brier (−0.013) |
| Goal probability calibration? | **Yes** — full_xg ECE improves by −0.050 |

**Trade-off:** `top5_xg` wins on accuracy; `full_xg` wins on calibration metrics. Neither is production-ready under strict significance rules.

---

## Part E — Feature Pruning

Global classification (pooled importance across Goal Range + Team Goals, with First Goal Team harm overlay):

| Classification | Features |
|----------------|----------|
| **STRONG_POSITIVE** | `away_recent_xga`, `home_recent_xga`, `rolling_xg_3_away`, `rolling_xg_10_away`, `xg_momentum_difference` |
| **WEAK_POSITIVE** | `rolling_xg_3_home`, `defensive_weakness_difference`, `rolling_xg_10_home`, `attack_strength_difference`, `home_recent_xg` |
| **NEUTRAL** | `xg_difference` |
| **REMOVE** | `away_recent_xg`, `rolling_xg_5_home`, `rolling_xg_5_away`, all `rolling_xga_*` (zero model weight) |

**Note:** Features classified STRONG_POSITIVE for Goal Range / Team Goals are simultaneously **harmful when injected into First Goal Team**. This is the core market-specific finding.

### Features to Remove (global stack pruning)

- `away_recent_xg` — superseded by xGA and rolling windows
- `rolling_xg_5_home`, `rolling_xg_5_away` — redundant with 3/10 windows
- All `rolling_xga_*` — never used by model (0% importance)

### Features to Remain (for benefiting markets)

`away_recent_xga`, `home_recent_xga`, `rolling_xg_3_away`, `rolling_xg_10_away`, `xg_momentum_difference`, `rolling_xg_3_home`, `defensive_weakness_difference`, `rolling_xg_10_home`, `attack_strength_difference`

---

## Part F — XG_LITE vs FULL_XG

**XG_LITE** (6 features): `away_recent_xga`, `home_recent_xga`, `rolling_xg_10_away`, `rolling_xg_3_away`, `xg_momentum_difference`, `defensive_weakness_difference`

| Market | FULL vs LITE Δ Acc | Bootstrap CI | LITE wins? |
|--------|-------------------|--------------|------------|
| Goal Range | **−6.3%** (full better) | [−12.5%, −1.0%] | **No** (significant) |
| Team Goals | −2.5% (full better) | [−9.0%, +3.5%] | No |

**`lite_outperforms_full_markets`: 0**

XG_LITE does **not** outperform FULL_XG. For Goal Range, FULL_XG is statistically better than LITE. For Team Goals, curated **top5_xg** beats both LITE and FULL on accuracy.

---

## Part G — Statistical Analysis Summary

| Market | Arm | Δ Acc | Δ LogLoss | Δ Brier | Δ ECE | Bootstrap CI (Acc) | n |
|--------|-----|-------|-----------|---------|-------|-------------------|---|
| First Goal Team | full_xg | −4.7% | +0.048 | +0.018 | +0.033 | [−13.0%, +4.2%] | 192 |
| Goal Range | top10_xg | +6.3% | +0.064 | — | — | [−1.6%, +14.6%] | 192 |
| Goal Range | full_xg | +5.7% | +0.062 | — | — | [−2.1%, +14.1%] | 192 |
| Team Goals | top5_xg | +3.0% | −0.032 | −0.012 | −0.038 | [−4.0%, +10.0%] | 201 |
| Team Goals | full_xg | +2.5% | −0.036 | −0.013 | −0.050 | [−4.5%, +9.5%] | 201 |

No market achieves **strict 95% bootstrap significance** on accuracy vs baseline. Goal Range shows the strongest directional signal (P(improve) ≈ 93%). Team Goals shows consistent secondary-metric improvement.

---

## Part H — Production Readiness

| Market | Status | Rationale |
|--------|--------|-----------|
| First Goal Team | **NO_VALUE** | xG harms accuracy and calibration; use baseline-only |
| Goal Range | **RESEARCH_ONLY** | +6.3% with top10_xg but CI crosses zero; needs more data / arm validation |
| Team Goals | **RESEARCH_ONLY** | +3.0% accuracy + calibration gains; not statistically significant |

**No market is PRODUCTION_READY.**

---

## Part I — Required Answers

### 1. Should xG be used for First Goal Team?

**No.** Policy: `NO_XG_FOR_FIRST_GOAL_TEAM`. Full xG stack reduces accuracy by 4.7% and worsens calibration.

### 2. Should xG be used for Goal Range?

**Yes, in research/shadow only.** Best arm is `top10_xg` (+6.3% accuracy). Not production-ready until significance improves.

### 3. Should xG be used for Team Goals?

**Yes, in research/shadow only.** Best arm is `top5_xg` (+3.0% accuracy); `full_xg` improves logloss, Brier, and ECE. Not production-ready yet.

### 4. Which xG features should be removed?

- `away_recent_xg`
- `rolling_xg_5_home`, `rolling_xg_5_away`
- All `rolling_xga_*` features (unused)
- Entire xG stack for First Goal Team

### 5. Which xG features should remain?

**Goal Range (top10):** `away_recent_xga`, `home_recent_xga`, `rolling_xg_10_away`, `rolling_xg_3_away`, `xg_momentum_difference`, `rolling_xg_10_home`, `rolling_xg_3_home`, `defensive_weakness_difference`, `attack_strength_difference`, `xg_difference`

**Team Goals (top5):** `away_recent_xga`, `home_recent_xga`, `rolling_xg_10_away`, `rolling_xg_3_away`, `xg_momentum_difference`

### 6. Does XG_LITE outperform FULL_XG?

**No.** FULL_XG beats XG_LITE in both benefiting markets. Goal Range difference is statistically significant (−6.3% for LITE vs FULL).

### 7. Should xG ever enter production?

**Not yet as blanket EGIE.** Market-specific shadow promotion is justified for Goal Range and Team Goals after further validation. First Goal Team should remain xG-free permanently unless new evidence emerges.

### 8. What is the next highest-value research direction?

1. **Market-specific feature arms in shadow replay** — deploy `top10_xg` for Goal Range and `top5_xg` for Team Goals in backtest-only shadow, not full stack
2. **Expand sample** beyond 1,004 fixtures (especially Goal Range where CI is wide)
3. **Calibration-first arm for Team Goals** — compare top5 (accuracy) vs full (ECE) in live shadow
4. **Hard exclusion gate** — enforce `NO_XG_FOR_FIRST_GOAL_TEAM` in EGIE routing before any promotion work

---

## Final Recommendation

**`CONTINUE_XG_RESEARCH`**

xG has **market-specific value** but is **not ready for production deployment**. The path forward is per-market feature arms in shadow validation, not a universal xG feature stack.

| Constraint | Status |
|------------|--------|
| Production deploy | **NOT done** |
| Live predictions | **NOT modified** |
| WDE | **NOT modified** |
| SaaS logic | **NOT modified** |
| Phase 54G | **NOT started** |

---

## Artifacts

| File | Purpose |
|------|---------|
| `worldcup_predictor/egie/xg_backtest/market_specific_optimizer.py` | Optimizer engine |
| `scripts/phase54f7_market_specific_xg_optimization.py` | CLI runner |
| `scripts/validate_phase54f7_market_specific_xg_optimization.py` | Validation gate |
| `artifacts/phase54f7_market_specific_xg/market_specific_optimization.json` | Full results |
| `artifacts/phase54f7_market_specific_xg/validation.json` | Validation output |
