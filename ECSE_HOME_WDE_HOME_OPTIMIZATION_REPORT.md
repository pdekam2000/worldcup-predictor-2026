# ECSE HOME ∧ WDE HOME — Forensic Optimization

**Status:** `ECSE_HOME_RULE_NO_ROBUST_IMPROVEMENT`  
**Decision:** **A** — No robust improvement exists.

## Base rule (current best)

- Rule: ECSE Direction = HOME **AND** WDE = HOME
- N=62 · Wins=45 · Losses=17
- Accuracy=72.6%
- Coverage (of TF universe 168)=36.9%
- Worst fold=59.1%
- Wilson 95%: {'low': 0.6040722415667276, 'high': 0.8211908140090788, 'center': 0.7126315277879032}

## Failure clusters (17 losses)

```json
{
  "unexpected_draw": 9,
  "away_upset": 8
}
```

## Optimization result


### No superior rule

Some filters reach >=75% accuracy but violate N/coverage/worst-fold/concentration/stability constraints. The base 72.6% rule remains the strongest robust rule.

Near-misses (≥75% but failing other gates): 5

- `BASE+total_lambda_ge_2_4` n=40 acc=82.5% worst=71.4% cov=23.8% passes=False
- `BASE+total_lambda_ge_2_2` n=48 acc=77.1% worst=62.5% cov=28.6% passes=False
- `BASE+wde_home_p_ge_40` n=56 acc=75.0% worst=60.0% cov=33.3% passes=False
- `BASE+ecse_home_mass_ge_40` n=56 acc=75.0% worst=60.0% cov=33.3% passes=False
- `BASE+ecse_home_gap_ge_30` n=52 acc=75.0% worst=55.6% cov=31.0% passes=False

## ROI

ROI NOT AVAILABLE

Base priced: {'rule': ['ecse_direction=home_win', 'wde_decision=home_win'], 'n': 62, 'wins': 45, 'losses': 17, 'accuracy': 0.7258064516129032, 'coverage_of_universe': 0.36904761904761907, 'worst_fold': 0.5909090909090909, 'wilson_95': {'low': 0.6040722415667276, 'high': 0.8211908140090788, 'center': 0.7126315277879032}}
Priced block: `{"priced_n": 1, "average_odds": 1.4, "roi": 0.3999999999999999, "max_drawdown": 0.0, "profit_factor": Infinity}`

## Top numeric win vs loss gaps

```json
{
  "wde_home_p": {
    "win_mean": 0.7686,
    "loss_mean": 0.6955882352941176,
    "win_median": 0.855,
    "loss_median": 0.746,
    "diff_mean": 0.07301176470588233,
    "win_n": 45,
    "loss_n": 17,
    "direction_hint": "wins_higher"
  },
  "wde_draw_p": {
    "win_mean": 0.13913333333333333,
    "loss_mean": 0.1778235294117647,
    "win_median": 0.098,
    "loss_median": 0.159,
    "diff_mean": -0.03869019607843138,
    "win_n": 45,
    "loss_n": 17,
    "direction_hint": "wins_lower"
  },
  "wde_away_p": {
    "win_mean": 0.09240000000000001,
    "loss_mean": 0.12658823529411767,
    "win_median": 0.045,
    "loss_median": 0.10300000000000001,
    "diff_mean": -0.03418823529411766,
    "win_n": 45,
    "loss_n": 17,
    "direction_hint": "wins_lower"
  },
  "wde_confidence": {
    "win_mean": 0.6204222222222222,
    "loss_mean": 0.6124117647058823,
    "win_median": 0.635,
    "loss_median": 0.598,
    "diff_mean": 0.008010457516339886,
    "win_n": 45,
    "loss_n": 17,
    "direction_hint": "wins_higher"
  },
  "ecse_home_mass": {
    "win_mean": 0.7613424222222223,
    "loss_mean": 0.6955882352941176,
    "win_median": 0.855,
    "loss_median": 0.746,
    "diff_mean": 0.06575418692810464,
    "win_n": 45,
    "loss_n": 17,
    "direction_hint": "wins_higher"
  },
  "ecse_draw_mass": {
    "win_mean": 0.13653333333333334,
    "loss_mean": 0.1778235294117647,
    "win_median": 0.089,
    "loss_median": 0.159,
    "diff_mean": -0.041290196078431374,
    "win_n": 45,
    "loss_n": 17,
    "direction_hint": "wins_lower"
  },
  "ecse_away_mass": {
    "win_mean": 0.09133333333333334,
    "loss_mean": 0.12658823529411767,
    "win_median": 0.034,
    "loss_median": 0.103,
    "diff_mean": -0.03525490196078433,
    "win_n": 45,
    "loss_n": 17,
    "direction_hint": "wins_lower"
  },
  "ecse_home_gap": {
    "win_mean": 0.6212535333333333,
    "loss_mean": 0.516,
    "win_median": 0.757,
    "loss_median": 0.599,
    "diff_mean": 0.10525353333333332,
    "win_n": 45,
    "loss_n": 17,
    "direction_hint": "wins_higher"
  }
}
```

## Safety

NOT DEPLOYED · CANONICAL UNCHANGED · WDE UNCHANGED · ECSE UNCHANGED · FREEZES UNCHANGED · NO PREDICTIONS REGENERATED · NO AUTO-PROMOTION · NO RESULT LEAKAGE

Success criterion met: honestly determined whether 72.6% can become a reliable ≥75% rule with meaningful N.
