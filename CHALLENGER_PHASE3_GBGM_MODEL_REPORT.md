# CHALLENGER PHASE 3 — GBGM MODEL REPORT

**Status:** `GBGM_CHALLENGER_BACKTEST_COMPLETE`
**Backends available:** ['lightgbm', 'sklearn_hist']
**Competitions:** ['world_cup_2026', 'champions_league', 'premier_league', 'bundesliga']

## Variants

- `GBGM-1-NM` — no market features
- `GBGM-1-MC` — market-calibrated (prematch implied odds only)

## Score distribution

Independent Poisson from predicted λ → labeled `GBGM_SCORE_DISTRIBUTION` (not ECSE).

## Safety

- Shadow only / non-public / no final decision authority
- Does not copy WDE Decision or ECSE Top5

```text
GBGM_CHALLENGER_BACKTEST_COMPLETE
```
