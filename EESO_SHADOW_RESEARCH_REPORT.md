# EESO Shadow Research Report

**Vienna:** 2026-07-13 17:35 CEST | **SHA:** c9764847ac974844078365de0c5e4f4b507b1fb2
**Final status:** `EESO_NO_PROVEN_ADVANTAGE`

## Executive answers

| # | Question | Answer |
|---|---|---|
| 1 | What already existed? | ~70–80% under `last8_team_form/` |
| 2 | What was reused? | profile_builder, shadow_selector, coverage_diagnostics, backtest loop |
| 3 | What was newly added? | EESO namespace, End Result metrics, named leagues, promotion gate |
| 4 | Last8 improve Top1? | Δ -3.334 pp (Top5 proxy; Top1 unchanged by selector) |
| 5 | Last8 improve Top3? | Δ 0.56 pp |
| 6 | Last8 improve Top5? | Δ -3.334 pp |
| 7 | Scenario diversification Top5? | Δ -0.23 pp |
| 8 | Hybrid Top5? | Δ -0.428 pp |
| 9 | End Result improved? | WDE 50.915% vs canonical Top5 ER 86.531% |
| 10 | xG value? | Not available pre-kickoff in replay — no lift |
| 11 | Pressure value? | Not available — no lift |
| 15 | 72,678 reproduced? | Paired=72678; canonical Top5=50.292% |
| 16 | +3pp Top5 lift? | **No** — best scenario_diversified_top5 +-0.23 pp |
| 17 | Production promotion? | **No** — shadow only |
| 18 | Remain shadow? | All EESO selectors |
| 19 | Next step? | Investigate probability generation tail mass before selector tuning |
| 20 | Final status | `EESO_NO_PROVEN_ADVANTAGE` |

## Backtest metrics

- Paired fixtures: **72678**
- Canonical Top1: **12.725%**
- Canonical Top3: **33.464%**
- Canonical Top5: **50.292%**
- Last8-aware Top5: **46.965%**
- Scenario diversified Top5: **50.069%**
- Hybrid Top5: **49.871%**

## End Result accuracy (separate from exact score)

{
  "wde_implied": 50.915,
  "top1": {
    "canonical_top1": 46.507,
    "canonical_top5": 46.507,
    "baseline_top5": 46.548,
    "wde_aligned_top5": 50.897,
    "scenario_diversified_top5": 46.548,
    "last8_aware_top5": 45.949,
    "hybrid_top5": 46.761
  },
  "top3": {
    "canonical_top3": 75.229,
    "raw_ecse_top3": 75.229,
    "wde_aligned_top3": 51.009,
    "last8_aware_top3": 76.96,
    "hybrid_coverage_top3": 76.052,
    "baseline_top5": 86.531
  },
  "top5": {
    "canonical_top5": 86.531,
    "baseline_top5": 86.531,
    "wde_aligned_top5": 51.031,
    "scenario_diversified_top5": 91.706,
    "last8_aware_top5": 98.553,
    "hybrid_top5": 95.717
  }
}

## Named league summary

{
  "world_cup": {
    "league_key": "world_cup",
    "label": "World Cup",
    "paired_fixture_count": 1352,
    "canonical_top1_pct": 10.651,
    "canonical_top3_pct": 30.473,
    "canonical_top5_pct": 45.932,
    "best_eeso_top3_pct": 45.932,
    "best_eeso_top5_pct": 46.746,
    "best_eeso_top3_method": "baseline_top5",
    "best_eeso_top5_method": "hybrid_top5",
    "net_lift_top5_pp": 0.814,
    "net_lift_top3_pp": 15.459,
    "end_result_canonical_top5_pct": 82.84,
    "end_result_best_eeso_pct": 97.485,
    "sample_warning": null,
    "promotion_eligible": false
  },
  "uefa": {
    "league_key": "uefa",
    "label": "UEFA competitions",
    "paired_fixture_count": 1869,
    "canonical_top1_pct": 12.413,
    "canonical_top3_pct": 32.21,
    "canonical_top5_pct": 48.743,
    "best_eeso_top3_pct": 48.743,
    "best_eeso_top5_pct": 49.331,
    "best_eeso_top3_method": "baseline_top5",
    "best_eeso_top5_method": "hybrid_top5",
    "net_lift_top5_pp": 0.588,
    "net_lift_top3_pp": 16.533,
    "end_result_canonical_top5_pct": 86.196,
    "end_result_best_eeso_pct": 98.876,
    "sample_warning": null,
    "promotion_eligible": false
  },
  "allsvenskan": {
    "league_key": "allsvenskan",
    "label": "Allsvenskan",
    "paired_fixture_count": 789,
    "canonical_top1_pct": 11.407,
    "canonical_top3_pct": 30.038,
    "canonical_top5_pct": 44.233,
    "best_eeso_top3_pct": 44.233,
    "best_eeso_top5_pct": 45.881,
    "best_eeso_top3_method": "baseline_top5",
    "best_eeso_top5_method": "hybrid_top5",
    "net_lift_top5_pp": 1.648,
    "net_lift_top3_pp": 14.195,
    "end_result_canonical_top5_pct": 85.298,
    "end_result_best_eeso_pct": 97.465,
    "sample_warning": null,
    "promotion_eligible": false
  },
  "eliteserien": {
    "league_key": "eliteserien",
    "label": "Eliteserien",
    "paired_fixture_count": 778,
    "canonical_top1_pct": 8.997,
    "canonical_top3_pct": 27.892,
    "canonical_top5_pct": 42.802,
    "best_eeso_top3_pct": 42.802,
    "best_eeso_top5_pct": 41.388,
    "best_eeso_top3_method": "baseline_top5",
    "best_eeso_top5_method": "hybrid_top5",
    "net_lift_top5_pp": -1.414,
    "net_lift_top3_pp": 14.91,
    "end_result_canonical_top5_pct": 83.162,
    "end_result_best_eeso_pct": 95.887,
    "sample_warning": null,
    "promotion_eligible": false
  },
  "urvalsdeild": {
    "league_key": "urvalsdeild",
    "label": "Urvalsdeild",
    "paired_fixture_count": 545,
    "canonical_top1_pct": 9.174,
    "canonical_top3_pct": 25.688,
    "canonical_top5_pct": 39.633,
    "best_eeso_top3_pct": 39.633,
    "best_eeso_top5_pct": 39.633,
    "best_eeso_top3_method": "baseline_top5",
    "best_eeso_top5_method": "scenario_diversified_top5",
    "net_lift_top5_pp": 0.0,
    "net_lift_top3_pp": 13.945,
    "end_result_canonical_top5_pct": 82.569,
    "end_result_best_eeso_pct": 94.679,
    "sample_warning": null,
    "promotion_eligible": false
  },
  "one_deild": {
    "league_key": "one_deild",
    "label": "1. deild Iceland",
    "paired_fixture_count": 0,
    "canonical_top1_pct": 0.0,
    "canonical_top3_pct": 0.0,
    "canonical_top5_pct": 0.0,
    "best_eeso_top3_pct": 0.0,
    "best_eeso_top5_pct": 0.0,
    "best_eeso_top3_method": "none",
    "best_eeso_top5_method": "none",
    "net_lift_top5_pp": 0.0,
    "net_lift_top3_pp": 0.0,
    "end_result_canonical_top5_pct": 0.0,
    "end_result_best_eeso_pct": 0.0,
    "sample_warning": "INSUFFICIENT_LEAGUE_SAMPLE",
    "promotion_eligible": false
  },
  "veikkausliiga": {
    "league_key": "veikkausliiga",
    "label": "Veikkausliiga",
    "paired_fixture_count": 580,
    "canonical_top1_pct": 12.414,
    "canonical_top3_pct": 31.724,
    "canonical_top5_pct": 47.931,
    "best_eeso_top3_pct": 47.931,
    "best_eeso_top5_pct": 47.759,
    "best_eeso_top3_method": "baseline_top5",
    "best_eeso_top5_method": "hybrid_top5",
    "net_lift_top5_pp": -0.172,
    "net_lift_top3_pp": 16.207,
    "end_result_canonical_top5_pct": 87.414,
    "end_result_best_eeso_pct": 98.276,
    "sample_warning": null,
    "promotion_eligible": false
  },
  "superettan": {
    "league_key": "superettan",
    "label": "Superettan",
    "paired_fixture_count": 133,
    "canonical_top1_pct": 8.271,
    "canonical_top3_pct": 26.316,
    "canonical_top5_pct": 42.105,
    "best_eeso_top3_pct": 42.105,
    "best_eeso_top5_pct": 43.609,
    "best_eeso_top3_method": "baseline_top5",
    "best_eeso_top5_method": "scenario_diversified_top5",
    "net_lift_top5_pp": 1.504,
    "net_lift_top3_pp": 15.789,
    "end_result_canonical_top5_pct": 93.233,
    "end_result_best_eeso_pct": 96.241,
    "sample_warning": null,
    "promotion_eligible": false
  },
  "virsliga": {
    "league_key": "virsliga",
    "label": "Virsliga",
    "paired_fixture_count": 364,
    "canonical_top1_pct": 12.363,
    "canonical_top3_pct": 30.769,
    "canonical_top5_pct": 45.879,
    "best_eeso_top3_pct": 45.879,
    "best_eeso_top5_pct": 44.231,
    "best_eeso_top3_method": "baseline_top5",
    "best_eeso_top5_method": "hybrid_top5",
    "net_lift_top5_pp": -1.648,
    "net_lift_top3_pp": 15.11,
    "end_result_canonical_top5_pct": 83.242,
    "end_result_best_eeso_pct": 96.978,
    "sample_warning": null,
    "promotion_eligible": false
  },
  "a_lyga": {
    "league_key": "a_lyga",
    "label": "A Lyga",
    "paired_fixture_count": 312,
    "canonical_top1_pct": 10.256,
    "canonical_top3_pct": 27.885,
    "canonical_top5_pct": 46.154,
    "best_eeso_top3_pct": 46.154,
    "best_eeso_top5_pct": 45.833,
    "best_eeso_top3_method": "baseline_top5",
    "best_eeso_top5_method": "scenario_diversified_top5",
    "net_lift_top5_pp": -0.321,
    "net_lift_top3_pp": 18.269,
    "end_result_canonical_top5_pct": 82.692,
    "end_result_best_eeso_pct": 98.077,
    "sample_warning": null,
    "promotion_eligible": false
  },
  "_total_paired_fixtures": 72678
}

## Promotion gate

{
  "checks": {
    "min_paired_fixtures": true,
    "no_leakage_assumed": true,
    "top5_lift_ge_3pp": false,
    "top3_not_degraded": true,
    "end_result_not_degraded": true,
    "multiple_leagues_improve": true,
    "validator_passed": true,
    "no_automatic_promotion": true
  },
  "recommend_production_promotion": false,
  "min_paired_fixtures": 1000,
  "required_top5_lift_pp": 3.0
}

## Forensic cases

### None (fixture 1494202)
- Actual: None
- Canonical Top5: None
- Diagnostics: None
- Analysis: {}

### KA Akureyri vs IA Akranes (fixture 1508804)
- Actual: None
- Canonical Top5: ['1-1', '1-2', '2-1', '0-1', '1-0']
- Diagnostics: ['NO_HIGH_SCORE_TAIL']
- Analysis: {"top10_contains_3_2": false, "high_score_tail_underweighted": true, "failure_layer": "probability_generation", "eeso_would_capture": null}
