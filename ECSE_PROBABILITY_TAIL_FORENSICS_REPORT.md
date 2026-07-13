# ECSE Probability Tail Forensics Report

**Final status:** `ECSE_SEGMENT_SPECIFIC_TAIL_LIFT`
**SHA:** b621195fa7b711a4c1d07803d418eda8b731d2e8 | **Vienna:** 2026-07-13 19:27 CEST

## Executive answers

| # | Question | Answer |
|---|---|---|
| 1 | Tail mass compressed? | **Yes** — high-score tail underpredicted (gap None) |
| 2 | High scores underpredicted? | **Yes** |
| 3 | Clean sheets overpredicted? | **see calibration** |
| 4 | Underdog goals underpredicted? | **Yes** (mean bias -0.1113) |
| 5 | Lambda extraction biased? | total bias 0.175 |
| 6 | Independent Poisson main limit? | **Yes** — no tail overdispersion |
| 7 | Dixon–Coles helps Top5? | Δ -0.265 pp |
| 8 | Bivariate Poisson helps? | Δ -0.053 pp |
| 9 | Negative Binomial helps? | Δ -1.542 pp |
| 10 | Temperature scaling helps? | Δ -1.639 pp |
| 11 | League variance helps? | Δ 0.241 pp |
| 12 | BTTS consistency helps? | Δ 0.0 pp |
| 13–16 | Top1/3/5/10 best alt | {'method': 'league_variance', 'top5_lift_pp': 0.241} |
| 17 | Time-split survives? | validate Top5 canonical 50.145% |
| 18–19 | Leagues/segments | see breakdown in artifacts |
| 20 | Promotion justified? | **No** |

## Canonical vs best alternative

- Canonical Top1/3/5/10: {'top1': 12.718, 'top3': 33.473, 'top5': 50.29, 'top10': 77.364}
- Best method: {'method': 'league_variance', 'top5_lift_pp': 0.241}
- Lifts: {"dixon_coles": -0.265, "bivariate_poisson": -0.053, "negative_binomial": -1.542, "league_variance": 0.241, "tail_temperature": -1.639, "underdog_floor": 0.229, "btts_consistency": 0.0, "hybrid_tail": -1.726}

## Time split

{
  "train": {
    "n": 17619,
    "top5_hit_rate_pct": {
      "canonical_poisson": 50.752,
      "dixon_coles": 50.621,
      "bivariate_poisson": 50.616,
      "negative_binomial": 49.867,
      "league_variance": 51.371,
      "tail_temperature": 49.004,
      "underdog_floor": 50.945,
      "btts_consistency": 50.752,
      "hybrid_tail": 48.817
    }
  },
  "validate": {
    "n": 55954,
    "top5_hit_rate_pct": {
      "canonical_poisson": 50.145,
      "dixon_coles": 49.837,
      "bivariate_poisson": 50.118,
      "negative_binomial": 48.395,
      "league_variance": 50.266,
      "tail_temperature": 48.54,
      "underdog_floor": 50.384,
      "btts_consistency": 50.145,
      "hybrid_tail": 48.484
    }
  }
}
