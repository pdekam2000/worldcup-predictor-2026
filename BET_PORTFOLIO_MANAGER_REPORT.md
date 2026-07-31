# BET_PORTFOLIO_MANAGER_REPORT

## Final status

**`BET_PORTFOLIO_MANAGER_RESEARCH_COMPLETE`**

**NOT DEPLOYED**

| Item | Value |
|---|---|
| Branch | `feature/bet-coverage-optimizer-64-tickets` |
| Base | Phase 5 `b816c3e` |
| Tests | **79 passed** |
| Historical fixtures | **1200** |
| Artifact path | `artifacts/bet_portfolio_manager/run_20260731T121944Z/` |
| Production deploy | **None** |

## Role

Portfolio Manager is the **capital decision layer**. It never changes football predictions.

Distinct from OBPE: OBPE selects markets; this package decides whether/how much to invest given Coverage + Insurance outputs (read-only).

## Historical validation (unit-stake, 1200 fixtures / 488 days)

| Metric | Always Bet | Portfolio Managed |
|---|---:|---:|
| Total staked | 1200 | **172** |
| Net return | 489.93 | 67.17 |
| ROI | 0.408 | 0.391 |
| Win frequency | 0.726 | **0.738** |
| Avg exposure / day | 2.46 | **0.35** |
| Max drawdown | 7.76 | **4.00** |
| Skipped days | 0 | **402** (82.4%) |

### Improvement summary

| Metric | Value |
|---|---:|
| ROI delta | **-0.018** |
| Drawdown improvement | **+3.76** |
| Capital efficiency (ROI delta) | -0.018 |
| Average skipped days | **402** |

Research reading: strong **exposure / drawdown reduction** and slightly higher win frequency on selected bets; **no ROI uplift yet** on this corpus. Continue forward shadow before any deployment.

## Portfolio grading distribution (historical days)

| Grade | Days |
|---|---:|
| B | 128 |
| C | 352 |
| D | 8 |

## Action distribution

| Action | Days |
|---|---:|
| WATCH | 400 |
| SMALL BET | 86 |
| SKIP | 2 |

## Sample day

| Field | Value |
|---|---|
| Score | 72.19 |
| Grade | B |
| Action | WATCH |

## Forward shadow

- Days stored: **12** (frozen stratum)
- Mostly SKIP/WATCH on thin frozen days — expected while HOLD from Phase 5

## Safety

- Canonical / ECSE / WDE / freezes unchanged
- Coverage Optimizer unchanged
- Insurance Optimizer unchanged
- Predictions not modified
- No production execution

## Docs

See `docs/BET_PORTFOLIO_MANAGER.md`.
