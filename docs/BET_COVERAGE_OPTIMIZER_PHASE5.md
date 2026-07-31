# Bet Coverage Optimizer — Phase 5: Long-Term Validation

**Status string:** `BET_COVERAGE_OPTIMIZER_PHASE5_LONG_TERM_VALIDATED`  
**Branch:** `feature/bet-coverage-optimizer-64-tickets`  
**Deploy:** **NOT DEPLOYED**

## Purpose

Final scientific validation before any Owner Shadow deployment.

- No new betting logic
- No new prediction formulas
- No ECSE / WDE / freeze / canonical changes

## Corpus

Primary replay uses **immutable ECSE formulas** on **prematch historical CSV odds** plus **real FT scores** from `external_historical_csv_raw_rows` (≥1000 fixtures).

Frozen prematch snapshots from `forward_prediction_tracking.db` are a separate forward-evidence stratum.

**Forbidden:** synthetic outcomes, fabricated odds, bookmaker simulation, post-match leakage.

## Runner

```bash
python scripts/run_bco_phase5_research.py --min-fixtures 1000 --max-historical 1500
```

## Deliverables

See `artifacts/coverage_optimizer/phase5_<timestamp>/` and `PHASE5_LONG_TERM_VALIDATION_REPORT.md`.
