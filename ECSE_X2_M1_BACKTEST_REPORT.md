# ECSE-X2-M1 — Backtest Comparison Report

**Fixtures evaluated:** 168,233  
**Success threshold passed:** NO  

## Overall — Baseline vs M1

| Metric | Baseline | M1 | Delta (M1 − Baseline) |
|--------|----------|-----|------------------------|
| Top-1 hit % | 10.6335 | 9.7805 | **-0.8530** |
| Top-3 hit % | 28.4332 | 26.1286 | **-2.3046** |
| Top-5 hit % | 42.7009 | 38.9139 | **-3.7870** |
| Top-10 hit % | 68.2286 | 61.7144 | **-6.5142** |
| Avg prob actual | 0.058996 | 0.057726 | -0.001270 |
| Avg log loss | 3.122161 | 3.31501 | +0.192849 |
| Avg Brier | 0.94031 | 0.950883 | +0.010573 |

## Success Criteria

- Top-1 ≥ +0.5pp: `-0.8530`
- Top-3 ≥ +1.0pp: `-2.3046`
- Log loss improved: `+0.192849`
- Met: `none`

## Special Test — High BTTS Yes + High Under 2.5

- Criteria: `btts_yes>0.58 and under_25>0.55`
- Fixtures: **3**
- Actual 1-1 hit rate: **33.3333%** (1 hits)
- 1-1 avg rank baseline → M1: **1.0 → 1.0**
- 1-1 top-1 when actual baseline/M1: **1 / 1**

## Rank shifts (actual score rank)

- Improved: **59,568**
- Worsened: **70,090**
- Unchanged: **38,575**

## By dominant quadrant (M1)

- **no_over** (n=1,166): top1=10.6346%, logloss=3.1669
- **no_under** (n=18,436): top1=14.3198%, logloss=2.672625
- **yes_over** (n=130,788): top1=8.6629%, logloss=3.472823
- **yes_under** (n=17,843): top1=13.2265%, logloss=2.831665

## By confidence bucket (M1)

- **high_ge_62** (n=88,309): top3=21.3908%
- **low_lt_55** (n=22,895): top3=33.8589%
- **med_55_62** (n=57,029): top3=30.3617%

## Top leagues (baseline)

- Premier League: baseline top1=12.052% → M1=11.532%
- Primera Division: baseline top1=11.2884% → M1=11.4441%
- Championship: baseline top1=13.125% → M1=12.5%
- League One: baseline top1=12.5568% → M1=12.6136%
- Super League: baseline top1=12.8571% → M1=11.3665%
- League Two: baseline top1=12.1803% → M1=10.8345%
- Serie A: baseline top1=12.2731% → M1=12.2004%
- Serie B: baseline top1=14.7338% → M1=14.6608%

---

*Research only. No retraining, deployment, or API calls.*