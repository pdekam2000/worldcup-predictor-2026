# ECSE Market Prior Shadow Research — ECSE-MARKET-PRIOR-SHADOW-1

**Generated:** 2026-07-04 21:59:49 UTC
**Mode:** research-only shadow — production ECSE unchanged

**Final recommendation:** `NEED_MORE_NATIONAL_TEAM_DATA`

## Part A — Canonical Dataset

- Rows: **77,204**
- Date range: 2022-09-20 → 2026-09-25
- Duplicate row_hash: 0

## Part I — Walk-Forward Backtest (chronological, no future leakage)

- Train N: 46322
- Validation N: 11581
- Holdout N: 19301
- Tuned alpha (validation only): **0.15**

### Holdout strategy comparison

| Strategy | N | Top1 % | Top3 % | Top5 % |
| --- | ---: | ---: | ---: | ---: |
| A_baseline_ecse | 1200 | 13.42 | 33.5 | 50.5 |
| B_market_blend | 1200 | 12.67 | 34.0 | 50.5 |
| C_diversified_top3 | 1200 | 13.42 | 34.58 | 50.5 |
| D_tail_calibration | 1200 | 12.58 | 32.92 | 50.5 |

### Part J — Top3 set agreement (ECSE vs market prior)

- **partial_2_3**: N=704 Top1=13.21% Top3=34.23%
- **partial_1_3**: N=289 Top1=13.84% Top3=33.22%
- **full_3_3**: N=179 Top1=15.64% Top3=34.08%
- **none_0_3**: N=28 Top1=0.0% Top3=14.29%

### Part D — K comparison (holdout baseline ECSE)

- K=25: Top3=35.0% (N=120)
- K=50: Top3=35.0% (N=120)
- K=100: Top3=35.0% (N=120)
- K=250: Top3=35.0% (N=120)
- K=500: Top3=35.0% (N=120)
- K=1000: Top3=35.0% (N=120)

### Part E — Time weighting (holdout blend)

- equal: Top3=34.17% (N=120)
- decay_365d: Top3=34.17% (N=120)
- last_2_seasons: Top3=34.17% (N=120)

### Part N — Negative controls

- ecse_baseline: Top3=40.0% (N=80)
- random_prior: Top3=2.5% (N=80)
- global_unconditional: Top3=37.5% (N=80)
- shuffled_neighbors: Top3=32.5% (N=80)

## Part M — Production controlled snapshot diagnostics (read-only)

### Colombia vs Ghana (1567310)
- Status: **MEDIUM_AGREEMENT**
- ECSE Top3: ['2-0', '1-0', '3-0']
- Market prior Top5: ['1-1', '3-0', '2-0', '2-1', '0-1']
- Set overlap: 2

### Canada vs Morocco (1567824)
- Status: **LOW_AGREEMENT**
- ECSE Top3: ['0-1', '0-2', '1-1']
- Market prior Top5: ['1-0', '2-0', '1-1', '2-1', '0-0']
- Set overlap: 1

### Paraguay vs France (1569870)
- Status: **LOW_AGREEMENT**
- ECSE Top3: ['0-2', '0-3', '0-4']
- Market prior Top5: ['2-0', '2-1', '3-0', '1-0', '3-1']
- Set overlap: 0

### Brazil vs Norway (1568100)
- Status: **LOW_AGREEMENT**
- ECSE Top3: ['2-0', '1-0', '2-1']
- Market prior Top5: ['1-1', '1-0', '0-0', '2-1', '1-2']
- Set overlap: 1


## Answers

1. Top1 improvement from market prior blend: -0.75 pp (blend vs baseline)
2. Top3 improvement: +0.50 pp (blend vs baseline)
3. Top5 improvement: +0.00 pp (blend vs baseline)
4. Best K (by Top3 on sampled holdout): K=25 (35.0%)
5. Recency weighting helps: No / marginal
6. Full Top3 agreement predictive: see agreement buckets above
7. Margin tail: underestimated cases logged = 216
8. Direct blending: 34.0% Top3
9. Diversification: 34.58% Top3
10. Tail calibration: 32.92% Top3
11. National-team evidence: insufficient in close-band historical source (domestic-heavy)
12. Safest next step: use as **diagnostic overlay** only; do not promote without national-team coverage

**STOP — no production promotion. Recommendation: `NEED_MORE_NATIONAL_TEAM_DATA`**