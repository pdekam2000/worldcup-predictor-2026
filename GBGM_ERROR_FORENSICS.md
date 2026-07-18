# GBGM ERROR FORENSICS

```json
{
  "by_bucket": {
    "bundesliga": {
      "n": 246,
      "mean_logloss": 1.194883325020488
    },
    "coverage:HIGH_COVERAGE": {
      "n": 299,
      "mean_logloss": 1.150827170900957
    },
    "high_goal": {
      "n": 127,
      "mean_logloss": 1.0370801329011656
    },
    "premier_league": {
      "n": 31,
      "mean_logloss": 0.9830145269277285
    },
    "low_goal": {
      "n": 49,
      "mean_logloss": 1.3828624333341317
    },
    "champions_league": {
      "n": 5,
      "mean_logloss": 0.8370726809952223
    },
    "world_cup_2026": {
      "n": 17,
      "mean_logloss": 0.9116007296829651
    }
  },
  "draw_underprediction_count": 66,
  "draw_underprediction_rate": 0.22073578595317725,
  "favourite_wrong_count": 165,
  "favourite_wrong_rate": 0.5518394648829431,
  "hypotheses": [
    "GBM may be overconfident vs league-average Poisson (higher LogLoss despite similar accuracy)",
    "Constant is_home + weak features \u2192 model adds noise relative to league means",
    "Mixed competitions with different scoring rates hurt a global booster",
    "Independent Poisson understates draws without Dixon\u2013Coles rho"
  ]
}
```

## Interpretation
- If LogLoss >> league baseline while accuracy is similar → overconfidence / miscalibration.
- Draw underprediction supports Dixon–Coles or calibration interventions.
- Domain buckets with worse mean LogLoss indicate global-model mismatch.