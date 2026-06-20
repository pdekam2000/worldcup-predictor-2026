# Phase 25 — Calibration + Shadow Replay Report

**Status:** Complete (local evaluation — no deployment, no gated auto-enable)

## Dataset

- **Total replay cases:** 32
- **Total replay rows (cases × stacks):** 288

| Source | Count |
|--------|-------|
| demo_wc2022_csv | 12 |
| synthetic_promotion_24a | 1 |
| synthetic_promotion_24b | 1 |
| synthetic_promotion_24c | 1 |
| synthetic_promotion_combo | 1 |
| wc2026_results_history | 16 |

## Promotion Modes Evaluated

1. **baseline** — all promotion flags `off`
2. **shadow_default** — all flags `shadow` (runtime default)
3. **gated_simulation** — isolated `gated` apply (does not change defaults)

## Metric Comparison

| Stack | Mode | N | 1X2 Acc | Avg Conf | Brier | Overconf | Review | Disagree | Flip | Promo Cov |
|-------|------|---|---------|----------|-------|----------|--------|----------|------|-----------|
| 24a_24b | gated_simulation | 32 | 40.6% | 48.6 | 0.237 | 3.1% | 0.0% | 0.0% | 0.0% | 9.4% |
| 24a_24b_24c | gated_simulation | 32 | 40.6% | 48.6 | 0.237 | 3.1% | 0.0% | 6.2% | 0.0% | 12.5% |
| 24a_only | gated_simulation | 32 | 40.6% | 48.6 | 0.237 | 3.1% | 0.0% | 0.0% | 0.0% | 6.2% |
| 24b_only | gated_simulation | 32 | 40.6% | 48.6 | 0.237 | 3.1% | 0.0% | 0.0% | 0.0% | 6.2% |
| 24c_sm_only | gated_simulation | 32 | 40.6% | 48.6 | 0.237 | 3.1% | 0.0% | 6.2% | 0.0% | 6.2% |
| 24c_xg_only | gated_simulation | 32 | 40.6% | 48.6 | 0.237 | 3.1% | 0.0% | 0.0% | 0.0% | 6.2% |
| baseline | baseline | 32 | 40.6% | 48.6 | 0.237 | 3.1% | 0.0% | 0.0% | 0.0% | 0.0% |
| gated_simulation | gated_simulation | 32 | 40.6% | 48.6 | 0.237 | 3.1% | 0.0% | 6.2% | 0.0% | 12.5% |
| shadow_default | shadow | 32 | 40.6% | 48.6 | 0.237 | 3.1% | 0.0% | 6.2% | 0.0% | 12.5% |

## Promotion Stack Comparison (gated simulation)

- **24a_24b**: acc 40.6%, flip 0.0%, avg Δconf +0.00, lineup Δ +0.50, context Δ +0.09, xG Δ +0.00, SM Δ +0.00
- **24a_24b_24c**: acc 40.6%, flip 0.0%, avg Δconf -0.19, lineup Δ +0.50, context Δ +0.09, xG Δ +0.05, SM Δ -0.19
- **24a_only**: acc 40.6%, flip 0.0%, avg Δconf +0.00, lineup Δ +0.50, context Δ +0.00, xG Δ +0.00, SM Δ +0.00
- **24b_only**: acc 40.6%, flip 0.0%, avg Δconf +0.00, lineup Δ +0.00, context Δ +0.09, xG Δ +0.00, SM Δ +0.00
- **24c_sm_only**: acc 40.6%, flip 0.0%, avg Δconf -0.19, lineup Δ +0.00, context Δ +0.00, xG Δ +0.00, SM Δ -0.19
- **24c_xg_only**: acc 40.6%, flip 0.0%, avg Δconf +0.00, lineup Δ +0.00, context Δ +0.00, xG Δ +0.05, SM Δ +0.00
- **gated_simulation**: acc 40.6%, flip 0.0%, avg Δconf -0.19, lineup Δ +0.50, context Δ +0.09, xG Δ +0.05, SM Δ -0.19

## Risk Analysis

- **confidence_inflation_cases:** 0
- **winner_flip_count:** 0
- **high_conflict_cases:** 0
- **gate_failure_without_signals:** 28
- **coverage_gap_cases:** 28
- **synthetic_signal_cases:** 4

## Recommended Flag Settings (manual approval required)

| Flag | Recommendation |
|------|----------------|
| `EXPECTED_LINEUP_PROMOTION_MODE` | **shadow** (default remains `shadow` until approved) |
| `TOURNAMENT_CONTEXT_PROMOTION_MODE` | **shadow** (default remains `shadow` until approved) |
| `XG_PROMOTION_MODE` | **shadow** (default remains `shadow` until approved) |
| `SPORTMONKS_PREDICTION_PROMOTION_MODE` | **shadow** (default remains `shadow` until approved) |

## Next Step Recommendation

1. Continue **shadow** defaults for all four promotion flags.
2. Expand replay with full specialist orchestrator snapshots when WC 2026 group-stage results accumulate.
3. Enable **gated** per promotion only after manual review of this report and live shadow JSONL.
4. Phase 25 weight calibration deferred — WDE weights unchanged.

Replay JSONL: `data\shadow\phase25_promotion_replay.jsonl`
Metrics JSON: `data\shadow\phase25_promotion_metrics.json`

**Phase 25 complete. Deployment not started.**
