# BET_COVERAGE_OPTIMIZER_PHASE3_INSURANCE_AND_REAL_ODDS_VALIDATION

## Final status

**`BET_COVERAGE_OPTIMIZER_PHASE3_INSURANCE_VALIDATED`**

**NOT DEPLOYED**

| Item | Value |
|---|---|
| Branch | `feature/bet-coverage-optimizer-64-tickets` |
| Base Phase 2 | `a47f677` |
| Tests | **61 passed** (`tests/research/bet_coverage_optimizer`) |
| Artifact path | `artifacts/coverage_optimizer/phase3_20260731T003925Z/` (gitignored) |
| Production deploy | **None** |

## Files changed (high level)

- `worldcup_predictor/research/bet_coverage_optimizer/insurance/` (uncovered mass, candidates, scoring, optimizer, real odds, budget, comparison, backtest)
- `worldcup_predictor/research/bet_coverage_optimizer/config.py` + `default_config.json` (insurance + budget blocks)
- `scripts/run_bco_phase3_research.py`
- `tests/research/bet_coverage_optimizer/test_phase3_insurance.py`
- `data/research/interwetten_three_fixture_markets.json`
- `docs/BET_COVERAGE_OPTIMIZER_PHASE3.md`
- this report

## Research results (€400 budget, Top8, Interwetten transcription + ResearchBook)

### Top insurance candidate per fixture

| Fixture | Primary covered mass | Insurance recovered | Final covered mass | Top insurance |
|---:|---:|---:|---:|---|
| 1556628 Dundee–Rangers | 0.749 | 0.110 | 0.859 | BTTS Yes @ 2.10 |
| 1494717 Bodø–Lillestrøm | 0.767 | 0.118 | 0.885 | BTTS No @ 1.55 |
| 1567860 Admira–Rapid II | 0.812 | 0.050 | 0.862 | BTTS Yes @ 1.92 |

### Tickets & budget

| Item | Value |
|---|---|
| Main tickets | **64** |
| Insurance tickets | **8** (≤15, not 125) |
| Total budget | **€400** |
| Main budget (80%) | **€320** → €5.00 / main ticket |
| Insurance budget (20%) | **€80** (score-weighted; capped) |
| Allocated | **€399.50** |
| Remainder | **€0.50** |
| Max theoretical loss | allocated stake only |

### Safety

- Canonical WDE/ECSE formulas unchanged
- Existing freezes unchanged
- Shadow models not promoted
- Odds never fabricated
- Manual screenshot source explicitly labeled non-API
- Phase 2 regressions remain green

## Docs

See `docs/BET_COVERAGE_OPTIMIZER_PHASE3.md` for Insurance vs Main Coverage, uncovered-mass math, real-odds rules, stake modes, and EV vs hit-mass interpretation.
