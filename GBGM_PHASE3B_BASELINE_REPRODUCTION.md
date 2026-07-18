# GBGM PHASE 3B — BASELINE REPRODUCTION

Exact Phase 3 holdout metrics reproduced from `artifacts/challenger_program/phase3_backtest.json` (no model changes).

- Dataset version: `challenger-bt-v1`
- Competitions: `['world_cup_2026', 'champions_league', 'premier_league', 'bundesliga']`
- Fixtures (usable): **1491** (blocked snapshots: 587)
- Split NM: train=894, val=298, holdout=299
- Train end: `2023-12-30T15:00:00`
- Validation end: `2024-05-04T13:30:00`
- Holdout end: `2026-07-15T19:00:00`

## Holdout 1X2 LogLoss
- League-average baseline: **1.0678**
- GBGM-1-NM (sklearn_hist): **1.1974**
- GBGM-1-MC (lightgbm): **1.2094**

## Full NM holdout metrics (selected backend)
```json
{
  "n": 299,
  "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
  "acc_1x2": 0.451505016722408,
  "brier_1x2": 0.7096909926086957,
  "logloss_1x2": 1.1974416660640839,
  "brier_btts": 0.26852618732441474,
  "logloss_btts": 0.7329372368426366,
  "acc_btts": 0.48494983277591974,
  "brier_ou25": 0.24901727969899665,
  "logloss_ou25": 0.6965382407041816,
  "acc_ou25": 0.568561872909699,
  "top1_hit": 0.06020066889632107,
  "top3_hit": 0.18729096989966554,
  "top5_hit": 0.3010033444816054,
  "top10_hit": 0.5518394648829431,
  "bootstrap_acc_1x2": {
    "mean": 0.451505016722408,
    "low": 0.39464882943143814,
    "high": 0.5083612040133779,
    "n": 299
  }
}
```

## League-average holdout
```json
{
  "n": 299,
  "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
  "acc_1x2": 0.4414715719063545,
  "brier_1x2": 0.6471249676923085,
  "logloss_1x2": 1.067766257172385,
  "brier_btts": 0.24318289090301,
  "logloss_btts": 0.6795360845245159,
  "acc_btts": 0.5886287625418061,
  "brier_ou25": 0.23532833685618726,
  "logloss_ou25": 0.6635253236538554,
  "acc_ou25": 0.6220735785953178,
  "top1_hit": 0.0903010033444816,
  "top3_hit": 0.22073578595317725,
  "top5_hit": 0.34448160535117056,
  "top10_hit": 0.5986622073578596,
  "bootstrap_acc_1x2": {
    "mean": 0.4414715719063545,
    "low": 0.38461538461538464,
    "high": 0.4983277591973244,
    "n": 299
  }
}
```

- Bookmaker baseline: not_available_in_phase3_artifact
- Canonical metrics: not_mixed_reconstructed_research_only

Shadow flags unchanged: is_shadow=true, public_visible=false, final_decision_authority=false.

Status: `BASELINE_REPRODUCTION_COMPLETE`