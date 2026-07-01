# DATA-1E Baseline Backtest Report

**Generated:** 2026-06-29 09:23:57 UTC

## Dataset

| Metric | Value |
|--------|-------|
| Join rows | 2062130 |
| Evaluable rows | 2060830 |
| Unevaluable rows | 1300 |
| Expected join rows (DATA-1D) | 2062130 |

## Strategy ROI summary

| Strategy | Bets | Hit rate % | Avg odds | ROI % | Profit |
|----------|------|------------|----------|-------|--------|
| A_all_selections | 2060830 | 69.2097 | 1.4256 | -5.262 | -108440.16 |
| B_odds_gte_2 | 103424 | 42.6961 | 2.3067 | -4.7419 | -4904.25 |
| C_odds_gte_3_5 | 3527 | 23.5611 | 4.9273 | 9.0859 | 320.46 |
| D_odds_3_5_to_12 | 3443 | 23.8164 | 4.7083 | 7.3035 | 251.46 |
| E_top_odds_per_fixture_market | 792475 | 58.5849 | 1.6778 | -5.3274 | -42218.56 |
| F_closing_only | 2060830 | 69.2097 | 1.4256 | -5.262 | -108440.16 |
| G_opening_odds | 2060830 | 69.2097 | 1.4286 | -4.8708 | -100379.79 |
| G_closing_odds | 2060830 | 69.2097 | 1.4256 | -5.262 | -108440.16 |

## Opening vs closing (strategy G)

- Opening ROI %: -4.8708
- Closing ROI %: -5.262
- Delta (closing - opening) ROI %: -0.3912

## Notes

- Research-only baseline; not production predictions.
- Stake = 1 unit per bet; ROI = (returns - stakes) / stakes × 100.
- Default odds: closing with opening fallback (except F/G variants).
- No API calls; no WDE/EGIE/ECSE changes.
