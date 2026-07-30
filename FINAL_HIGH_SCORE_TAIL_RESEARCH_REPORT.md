# FINAL HIGH SCORE TAIL RESEARCH REPORT

## Status

`HIGH_SCORE_TAIL_RESEARCH_COMPLETE_SHADOW_PARTIAL`

## Confirmed root causes

1. **Lambda underestimation** on high-score fixtures (positive total λ error on totals 4 / 5+).
2. **Grid truncation** at MAX_GOALS=7 pushes extreme scorelines into OTHER; renormalization does not create named high-score cells.
3. **Over-dispersion** helps modestly for coverage (NB / ensemble) but cannot fix zeros when λ totals are far below actuals.
4. **Market O/U** signal helps regime selection more than raw Top5 when odds columns are sparse.
5. Favorite blowout / underdog tails help segment diagnostics; limited sample for promotion.

## Cohort evidence (canonical n=168)

- total_4: n=18 Top5=0.1111 λ_err=1.3773
- total_5plus: n=31 Top5=0.0323 λ_err=3.1057

## Best models (validation)

### Global Top5
[
  {
    "n": 42,
    "top1": 0.1667,
    "top3": 0.3095,
    "top5": 0.5238,
    "top10": 0.7381,
    "log_loss": 2.8566,
    "outside_named_grid_rate": 0.0,
    "avg_p_actual": 0.0855,
    "avg_p_4plus": 0.2105,
    "avg_p_5plus": 0.1122,
    "high_n": 11,
    "high_top5": 0.0,
    "high_top10": 0.1818,
    "low_n": 21,
    "low_top5": 0.9524,
    "challenger": "H9_underdog_tail",
    "split": "validation"
  },
  {
    "n": 42,
    "top1": 0.1667,
    "top3": 0.2857,
    "top5": 0.4762,
    "top10": 0.7143,
    "log_loss": 2.8872,
    "outside_named_grid_rate": 0.0,
    "avg_p_actual": 0.0867,
    "avg_p_4plus": 0.1934,
    "avg_p_5plus": 0.1014,
    "high_n": 11,
    "high_top5": 0.0,
    "high_top10": 0.1818,
    "low_n": 21,
    "low_top5": 0.9048,
    "challenger": "H6_market_total",
    "split": "validation"
  },
  {
    "n": 42,
    "top1": 0.1667,
    "top3": 0.2857,
    "top5": 0.4524,
    "top10": 0.7381,
    "log_loss": 2.8847,
    "outside_named_grid_rate": 0.0,
    "avg_p_actual": 0.0851,
    "avg_p_4plus": 0.1899,
    "avg_p_5plus": 0.0963,
    "high_n": 11,
    "high_top5": 0.0,
    "high_top10": 0.1818,
    "low_n": 21,
    "low_top5": 0.8571,
    "challenger": "H3_negative_binomial",
    "split": "validation"
  }
]

### High-score Top5
[
  {
    "n": 42,
    "top1": 0.1667,
    "top3": 0.3095,
    "top5": 0.5238,
    "top10": 0.7381,
    "log_loss": 2.8566,
    "outside_named_grid_rate": 0.0,
    "avg_p_actual": 0.0855,
    "avg_p_4plus": 0.2105,
    "avg_p_5plus": 0.1122,
    "high_n": 11,
    "high_top5": 0.0,
    "high_top10": 0.1818,
    "low_n": 21,
    "low_top5": 0.9524,
    "challenger": "H9_underdog_tail",
    "split": "validation"
  },
  {
    "n": 42,
    "top1": 0.1667,
    "top3": 0.2857,
    "top5": 0.4762,
    "top10": 0.7143,
    "log_loss": 2.8872,
    "outside_named_grid_rate": 0.0,
    "avg_p_actual": 0.0867,
    "avg_p_4plus": 0.1934,
    "avg_p_5plus": 0.1014,
    "high_n": 11,
    "high_top5": 0.0,
    "high_top10": 0.1818,
    "low_n": 21,
    "low_top5": 0.9048,
    "challenger": "H6_market_total",
    "split": "validation"
  },
  {
    "n": 42,
    "top1": 0.1667,
    "top3": 0.2857,
    "top5": 0.4524,
    "top10": 0.7381,
    "log_loss": 2.8847,
    "outside_named_grid_rate": 0.0,
    "avg_p_actual": 0.0851,
    "avg_p_4plus": 0.1899,
    "avg_p_5plus": 0.0963,
    "high_n": 11,
    "high_top5": 0.0,
    "high_top10": 0.1818,
    "low_n": 21,
    "low_top5": 0.8571,
    "challenger": "H3_negative_binomial",
    "split": "validation"
  }
]

### Low-score Top5
[
  {
    "n": 42,
    "top1": 0.1667,
    "top3": 0.3095,
    "top5": 0.5238,
    "top10": 0.7381,
    "log_loss": 2.8566,
    "outside_named_grid_rate": 0.0,
    "avg_p_actual": 0.0855,
    "avg_p_4plus": 0.2105,
    "avg_p_5plus": 0.1122,
    "high_n": 11,
    "high_top5": 0.0,
    "high_top10": 0.1818,
    "low_n": 21,
    "low_top5": 0.9524,
    "challenger": "H9_underdog_tail",
    "split": "validation"
  },
  {
    "n": 42,
    "top1": 0.1667,
    "top3": 0.2857,
    "top5": 0.4762,
    "top10": 0.7143,
    "log_loss": 2.8872,
    "outside_named_grid_rate": 0.0,
    "avg_p_actual": 0.0867,
    "avg_p_4plus": 0.1934,
    "avg_p_5plus": 0.1014,
    "high_n": 11,
    "high_top5": 0.0,
    "high_top10": 0.1818,
    "low_n": 21,
    "low_top5": 0.9048,
    "challenger": "H6_market_total",
    "split": "validation"
  },
  {
    "n": 42,
    "top1": 0.1667,
    "top3": 0.2857,
    "top5": 0.4524,
    "top10": 0.7381,
    "log_loss": 2.8847,
    "outside_named_grid_rate": 0.0,
    "avg_p_actual": 0.0851,
    "avg_p_4plus": 0.1899,
    "avg_p_5plus": 0.0963,
    "high_n": 11,
    "high_top5": 0.0,
    "high_top10": 0.1818,
    "low_n": 21,
    "low_top5": 0.8571,
    "challenger": "H3_negative_binomial",
    "split": "validation"
  }
]

## Regime selector

{
  "selected_top5": {
    "n": 84,
    "rate": 0.4762
  },
  "freeze_top5": {
    "n": 84,
    "rate": 0.4643
  },
  "selected_on_high_actual": {
    "n": 22,
    "rate": 0.0
  },
  "freeze_on_high_actual": {
    "n": 22,
    "rate": 0.0
  },
  "selected_on_low_actual": {
    "n": 45,
    "rate": 0.8444
  },
  "freeze_on_low_actual": {
    "n": 45,
    "rate": 0.8222
  },
  "regime_counts": {
    "LOW_SCORE": 38,
    "HIGH_SCORE": 17,
    "UNCLEAR": 29
  }
}

## Shadow implementation

{
  "shadow_rows_written_this_run": 504,
  "shadow_table_total": 504,
  "canonical_untouched": true,
  "forward_minima": {
    "dixon_coles_review": 150,
    "high_score_specialist_review": 75,
    "global_promotion": 250
  },
  "forward_shadow_ready": true,
  "production_eligible": false
}

## Production eligibility

**Not eligible.** Shadow-only. Need ≥150 forward DC fixtures and ≥75 high-score-risk fixtures before review; ≥250 before any global promotion discussion.
