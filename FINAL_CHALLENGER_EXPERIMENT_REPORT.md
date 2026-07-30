# FINAL CHALLENGER EXPERIMENT REPORT

## Scope

Isolated research challengers on **canonical one-freeze-per-fixture** dataset (n=168), time-ordered 60/40 train/validation by kickoff.  
No freeze mutation. No production promotion.

Artifact: `artifacts/dataset_reconciliation_experiments/20260730T125305Z/challenger_experiments/`

## Validation baseline (frozen ECSE tops)

- n_valid ≈ 68
- Top1 19.1% / Top5 **50.0%** / Top10 (from freeze flags on valid slice)
- High-score (≥4 goals) Top5: **0.0%** on validation high-score subset

## Experiment results (validation)

| Challenger | Top1 | Top5 | ΔTop5 | High-score Top5 | Low-score Top5 | Notes |
|------------|------|------|-------|-----------------|----------------|-------|
| G1 dynamic tail | 0.191 | 0.500 | 0.000 | 0.000 | — | No gain |
| G2 λ recalibration | 0.118 | 0.485 | −0.015 | 0.000 | — | Regresses |
| **G3 Dixon–Coles** | 0.162 | **0.544** | **+0.044** | 0.000 | **0.882** | Best Top5; Top1 regresses; **no high-score help** |
| G4 bivariate | 0.206 | 0.500 | 0.000 | 0.000 | — | Top1 slight lift |
| G5 rank calibration | 0.191 | 0.500 | 0.000 | 0.000 | — | No gain |
| G6 ensemble | 0.221 | 0.500 | 0.000 | 0.000 | — | Best Top1 among set; Top5 flat |

### Best challenger (retrospective only)

**G3_dixon_coles** — best validation Top5 (+4.4 pp) via low-score correction.

**Must remain shadow-only** because:

1. High-score tail still **0% Top5** on validation
2. Top1 regresses vs freeze baseline
3. Validation n=68 is modest; no forward shadow yet
4. Challenger redistributes from λ, not identical to production ECSE blend

### WDE experiments

Disagreement between WDE pick and ECSE implied 1X2 mass predicts worse WDE accuracy (see `wde_calibration_experiments.csv`).  
Proposed additive diagnostic: `proposed_wde_challenger.md` (severity flag for strategy layer; no probability rewrite).

### Strategy rebuild (canonical n=168)

| Tier | n | Coverage | Top5 | WDE |
|------|--:|---------:|-----:|----:|
| Watchlist | 83 | 49% | 48.2% | 54.2% |
| No Bet | 52 | 31% | 44.2% | 25.0% |
| Tier A | 21 | 12.5% | 33.3% | 66.7% |
| Tier S | 12 | 7.1% | 50.0% | 83.3% |

**Do not promote Tier S** — n=12 too small; Top1 worse than Watchlist.

### Forward-shadow recommendation

1. Shadow-log G3 Dixon–Coles tops alongside canonical ECSE
2. Shadow-log WDE↔ECSE severity diagnostic
3. Minimum forward sample before any promotion discussion: **≥150** settled fixtures (≥30 high-score)
4. Reject promotion if high-score Top5 does not improve
