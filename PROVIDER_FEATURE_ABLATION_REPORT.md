# Provider Feature Ablation Report

Baseline: A_baseline_production_odds

| Family | Variant | N | Δ accuracy | Log loss | Cal error | ECSE Top1 | Flags |
|--------|---------|---|------------|----------|-----------|-----------|-------|
| odds | B_baseline_plus_odds_features | 11554 | 0.0006 | 1.0020900493618017 | 0.006 | 0.0 |  |
| xg | C_baseline_plus_xg_diagnostic | 11554 | 0.0003 | 0.9980372840908035 | 0.0208 | 0.0 | POST_MATCH_xG_diagnostic_non_promotable |
| form | D_baseline_plus_form_proxy | 11554 | -0.0002 | 1.0024359443995134 | 0.0128 | 0.0 |  |
| lineup_injury | E_baseline_plus_lineup_injury_proxy | 11554 | 0.0 | 1.0024393699241971 | 0.0127 | 0.0 | insufficient_stored_coverage_proxy_only |
| pressure | F_baseline_plus_pressure_proxy | 11554 | 0.0 | 1.0024393699241971 | 0.0127 | 0.0 | insufficient_stored_coverage_proxy_only |
| odds_xg | G_baseline_plus_odds_and_xg_diagnostic | 11554 | 0.0039 | 0.9971371769827694 | 0.0171 | 0.0 | POST_MATCH_xG_diagnostic_non_promotable |
| full_safe | H_full_safe_fusion | 11554 | 0.0003 | 1.001998286329863 | 0.0038 | 0.0 |  |

Deltas computed on chronological holdout; xG family is diagnostic-only (post-match leakage).
