# WDE Shadow Training & Backtest Report

**Phase:** WDE-RETRAIN-SHADOW-2  
**Mode:** Owner/internal research only — shadow model, no production replacement  
**Generated:** 2026-07-01 09:46:10 UTC

## Split summary

| Split | Rows | Date range |
|-------|------|------------|
| Train | 53,916 | 2022-09-20 → 2025-08-03 |
| Validation | 11,553 | 2025-08-03 → 2026-02-06 |
| Test | 11,554 | 2026-02-06 → 2026-07-01 |

- Strict time order: **True**
- No duplicate row_hash: **True**
- Dataset total (prep): **77,023**

## Model

- **Type:** `LightGBM`
- **Directory:** `models\shadow\wde_historical_csv_shadow_20260701`
- **Train rows:** 53,916
- **Validation rows:** 11,553

### Feature groups

- implied_market_probs: `True`
- xg_home_away_diff_total: `True`
- corners: `True`
- league_country_encoding: `True`
- season_year: `True`
- data_quality_flags: `True`
- no_final_score_features: `True`

## Validation metrics (during training)

| Market | Val accuracy | Bookmaker val accuracy | Beats bookmaker |
|--------|--------------|------------------------|-----------------|
| 1X2 | 0.5052 | 0.5083 | False |
| O/U2.5 | 0.5807 | 0.5775 | True |
| BTTS | 0.5512 | 0.5549 | False |

## Backtest — validation split

| Market | Shadow | Bookmaker | Historical | Current WDE |
|--------|--------|-----------|------------|-------------|
| 1X2 | 0.5052 | 0.5083 | 0.4294 | n/a |
| O/U2.5 | 0.5807 | 0.5775 | 0.5454 | n/a |
| BTTS | 0.5512 | 0.5549 | 0.5354 | n/a |

## Backtest — test split

| Market | Shadow | Bookmaker | Historical | Current WDE |
|--------|--------|-----------|------------|-------------|
| 1X2 | 0.4986 | 0.5060 | 0.4273 | n/a |
| O/U2.5 | 0.5820 | 0.5729 | 0.5282 | n/a |
| BTTS | 0.5640 | 0.5548 | 0.5385 | n/a |

### Current WDE comparison coverage (test)

- Matched predictions: **0** / 11554
- Coverage rate: **0.0**
- Note: Small coverage expected — historical CSV rows rarely map to production fixtures

## Best / worst (test, 1X2 accuracy, n≥50)

| Segment | Best | Worst |
|---------|------|-------|
| Competition | CO1 (0.5636) | MA1 (0.3226) |
| Country | World (0.6087) | South-Korea (0.4517) |

## Calibration (test 1X2)

0.20-0.40: conf=0.3761, acc=0.3497 (n=1690); 0.40-0.60: conf=0.488, acc=0.4593 (n=6421); 0.60-0.80: conf=0.6873, acc=0.6089 (n=2710); 0.80-1.00: conf=0.8542, acc=0.779 (n=733)

## Risks

- Historical CSV teams may not align with production fixture crosswalk → low WDE comparison coverage.
- Bookmaker implied baseline is strong; beating it on held-out test is difficult.
- O/U2.5 has fewer usable rows than 1X2/BTTS.
- Time-based split may under-represent recent leagues/seasons in test.

## Validation gate

- Checks passed: **12** / 12
- Promotion allowed: **False**

## Final recommendation

### `SHADOW_MODEL_BEATS_BOOKMAKER_BASELINE`

**No production model replacement. No public changes. No writes to worldcup_stored_predictions or odds_snapshots.**
