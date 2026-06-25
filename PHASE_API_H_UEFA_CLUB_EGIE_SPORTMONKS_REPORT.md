# PHASE API-H — UEFA Club EGIE Sportmonks Dataset

**Mode:** Audit → Ingest → Validate → Backtest → Report
**Production deploy:** NO

## Executive Summary

- **Fixtures mapped:** 120
- **Survival dataset:** `C:\Users\kaman\Desktop\Footbal\data\egie\uefa_club\uefa_survival_dataset.parquet`
- **Winning strategy:** D
- **Promotion safe:** True

## STEP 1 — League Coverage

| Competition | league_id | Fixtures sampled | Finished sampled |
|-------------|-----------|------------------|------------------|
| Champions League | 2 | 150 | 150 |
| Europa League | 5 | 150 | 150 |
| Europa Conference League | 2286 | 150 | 150 |
| UEFA Super Cup | 1326 | 0 | 0 |

API calls (coverage audit): 14

## STEP 2 — Fixture Mapping

Total fixtures: **120**
By competition: `{'champions_league': 40, 'europa_league': 40, 'conference_league': 40}`

## STEP 3 — Sportmonks Ingest

```json
{'skipped': True}
```

## STEP 4 — Provider Coverage

```json
{'fixtures': 120, 'coverage_count': {'xg': 0, 'pressure': 42, 'odds': 35, 'predictions': 0, 'lineups': 70, 'events': 65, 'statistics': 44}, 'coverage_pct': {'xg': 0.0, 'pressure': 35.0, 'odds': 29.17, 'predictions': 0.0, 'lineups': 58.33, 'events': 54.17, 'statistics': 36.67}}
```

## STEP 6 — A–F Backtest

| Strategy | FG Team | Goal Range | Soft Minute | Paid-data fixtures |
|----------|---------|------------|-------------|-------------------|
| A | 0.5 | 0.2462 | 0.3538 | 0/93 |
| B | 0.4615 | 0.2462 | 0.3538 | 0/93 |
| C | 0.4615 | 0.2462 | 0.3538 | 38/93 |
| D | 0.8372 | 0.2462 | 0.3538 | 32/93 |
| E | 0.8372 | 0.2462 | 0.3538 | 39/93 |
| F | 0.8372 | 0.2462 | 0.3538 | 65/93 |

## STEP 7 — Feature Impact Ranking

- **Tier B** — Strategy B (xG): FG delta -3.85 pp vs baseline
- **Tier B** — Strategy C (Pressure): FG delta -3.85 pp vs baseline
- **Tier S** — Strategy D (Odds): FG delta +33.72 pp vs baseline
- **Tier S** — Strategy E (Combined xG+Pressure+Odds): FG delta +33.72 pp vs baseline
- **Tier S** — Strategy F (Full Sportmonks): FG delta +33.72 pp vs baseline

## Recommendation

Use UEFA club competitions (CL/EL/Conference/Super Cup) for Sportmonks-enriched EGIE research. Do not deploy to production until a strategy beats baseline A by >1pp with stable calibration.

**STOP — no production deploy.**