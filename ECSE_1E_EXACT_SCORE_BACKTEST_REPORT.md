# ECSE-1E — Exact Score Backtest Report

**Backtest version:** `ECSE-1E-v1`  
**Distribution method:** `ECSE-1D-v1`  
**Generated:** 2026-06-29 12:37:45 UTC  
**Fixtures evaluated:** 168,233

## Overall ECSE Performance

| Metric | Value |
|--------|-------|
| Top-1 hit rate | **11.0674%** |
| Top-3 hit rate | **28.8665%** |
| Top-5 hit rate | **43.2394%** |
| Top-10 hit rate | **69.0352%** |
| Avg prob on actual score | 0.06014 |
| Avg log loss | 3.043873 |
| Avg Brier (multiclass) | 0.938625 |

## Baselines

| Baseline | Top-1 hit % | Notes |
|----------|-------------|-------|
| historical_mode | 10.4046% | 1-1 |
| naive_poisson_global_avg | 10.4046% | 1-1 |
| market_favorite_score_heuristic | 10.3654% | both odds: fav 1-0/0-1/1-1; single odds: short 1-0 or 0-1 else 1-1 |

## Breakdown by data quality

- **high_gte_0_60** (n=58188): top1=12.0283%, logloss=2.961005
- **low_lt_0_40** (n=32183): top1=11.6521%, logloss=3.003277
- **med_0_40_0_60** (n=77862): top1=10.1076%, logloss=3.122582

## Breakdown by lambda_total

- **high_gt_3_5** (n=43539): top1=8.8771%, top5=31.2754%
- **low_lt_2_5** (n=20467): top1=14.8678%, top5=60.3313%
- **med_2_5_3_5** (n=104227): top1=11.2361%, top5=44.8809%

## Breakdown by odds band

- **favorite_lt_1_80** (n=53548): top1=9.5055%
- **longshot_gt_2_50** (n=3070): top1=10.2606%
- **mid_1_80_2_50** (n=18584): top1=11.4292%
- **unknown** (n=93031): top1=11.9208%

## Top leagues (by volume)

- Premier League (n=5385): top1=12.4234%
- Primera Division (n=2569): top1=11.2884%
- Championship (n=1760): top1=13.1818%
- League One (n=1760): top1=12.5568%
- Super League (n=1610): top1=13.6025%
- League Two (n=1486): top1=12.1803%
- Serie A (n=1377): top1=12.2731%
- Serie B (n=1371): top1=14.7338%
- Division 1 (n=1287): top1=12.9759%
- U19 League (n=1284): top1=9.2679%

---

*Evaluation only. No training, tuning, or deployment.*