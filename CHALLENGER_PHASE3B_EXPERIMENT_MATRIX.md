# CHALLENGER PHASE 3B — EXPERIMENT MATRIX

| ID | Name | Val LogLoss | Holdout LogLoss | Holdout Brier |
| -- | ---- | ----------- | --------------- | ------------- |
| A | League baseline | 1.0928 | 1.0678 | 0.6471 |
| B | Team strength baseline | 0.9828 | 1.0092 | 0.6031 |
| C | GBGM-NM-v1 | 1.0897 | 1.1508 | 0.6885 |
| D | GBGM-NM-v2 | 1.0111 | 1.0113 | 0.6033 |
| E | GBGM-MC-v1 | 1.0897 | 1.1508 | 0.6885 |
| F | GBGM-MC-v2 | 1.0111 | 1.0113 | 0.6033 |
| G | Best (B) + Dixon–Coles | 0.9787 | 1.0096 | 0.6031 |
| H | Best (B) + Bivariate Poisson | 0.9737 | 1.0092 | 0.6025 |

## Calibration (validation-fitted temperature)
```json
{
  "method": "temperature",
  "T": 1.25,
  "base_experiment": "B",
  "validation_pre": {
    "n": 298,
    "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
    "acc_1x2": 0.5067114093959731,
    "brier_1x2": 0.5834457459395975,
    "logloss_1x2": 0.9827602823158157,
    "rps_1x2": 0.3816816210738256,
    "ece_1x2": 0.08140234899328859,
    "brier_btts": 0.24145488630872483,
    "logloss_btts": 0.6769643622518443,
    "acc_btts": 0.6208053691275168,
    "brier_ou25": 0.23519973939597316,
    "logloss_ou25": 0.6662505754781427,
    "acc_ou25": 0.6543624161073825,
    "exact_score_nll": 3.462838171254665,
    "top1_hit": 0.15100671140939598,
    "top3_hit": 0.2953020134228188,
    "top5_hit": 0.4261744966442953,
    "top10_hit": 0.6610738255033557,
    "expected_goal_mae": 0.9831981543624161,
    "expected_goal_rmse": 1.2449060983630897,
    "bootstrap_acc_1x2": {
      "mean": 0.5067114093959731,
      "low": 0.44966442953020136,
      "high": 0.5671140939597316,
      "n": 298
    }
  },
  "validation_post": {
    "n": 298,
    "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
    "acc_1x2": 0.5067114093959731,
    "brier_1x2": 0.5816302517114089,
    "logloss_1x2": 0.9802735183459961,
    "rps_1x2": 0.3820886533892617,
    "ece_1x2": 0.09159731543624157,
    "brier_btts": 0.24145488630872483,
    "logloss_btts": 0.6769643622518443,
    "acc_btts": 0.6208053691275168,
    "brier_ou25": 0.23519973939597316,
    "logloss_ou25": 0.6662505754781427,
    "acc_ou25": 0.6543624161073825,
    "exact_score_nll": 3.462838171254665,
    "top1_hit": 0.15100671140939598,
    "top3_hit": 0.2953020134228188,
    "top5_hit": 0.4261744966442953,
    "top10_hit": 0.6610738255033557,
    "expected_goal_mae": 0.9831981543624161,
    "expected_goal_rmse": 1.2449060983630897,
    "bootstrap_acc_1x2": {
      "mean": 0.5067114093959731,
      "low": 0.44966442953020136,
      "high": 0.5671140939597316,
      "n": 298
    }
  },
  "holdout_pre": {
    "n": 299,
    "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
    "acc_1x2": 0.5016722408026756,
    "brier_1x2": 0.6031214216053504,
    "logloss_1x2": 1.0091526576106071,
    "rps_1x2": 0.4323824997993313,
    "ece_1x2": 0.06506688963210701,
    "brier_btts": 0.24291926792642138,
    "logloss_btts": 0.6791961944145776,
    "acc_btts": 0.5919732441471572,
    "brier_ou25": 0.23510593872909696,
    "logloss_ou25": 0.6620717542244252,
    "acc_ou25": 0.5953177257525084,
    "exact_score_nll": 3.573397915286137,
    "top1_hit": 0.09698996655518395,
    "top3_hit": 0.23411371237458195,
    "top5_hit": 0.38461538461538464,
    "top10_hit": 0.6287625418060201,
    "expected_goal_mae": 1.0558215719063546,
    "expected_goal_rmse": 1.3106910050627907,
    "bootstrap_acc_1x2": {
      "mean": 0.5016722408026756,
      "low": 0.44481605351170567,
      "high": 0.5618729096989966,
      "n": 299
    }
  },
  "holdout_post": {
    "n": 299,
    "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
    "acc_1x2": 0.5016722408026756,
    "brier_1x2": 0.6008258661204012,
    "logloss_1x2": 1.005940684513755,
    "rps_1x2": 0.42998147531772596,
    "ece_1x2": 0.09524347826086957,
    "brier_btts": 0.24291926792642138,
    "logloss_btts": 0.6791961944145776,
    "acc_btts": 0.5919732441471572,
    "brier_ou25": 0.23510593872909696,
    "logloss_ou25": 0.6620717542244252,
    "acc_ou25": 0.5953177257525084,
    "exact_score_nll": 3.573397915286137,
    "top1_hit": 0.09698996655518395,
    "top3_hit": 0.23411371237458195,
    "top5_hit": 0.38461538461538464,
    "top10_hit": 0.6287625418060201,
    "expected_goal_mae": 1.0558215719063546,
    "expected_goal_rmse": 1.3106910050627907,
    "bootstrap_acc_1x2": {
      "mean": 0.5016722408026756,
      "low": 0.44481605351170567,
      "high": 0.
```

## Selection
```json
{
  "chosen_by_validation": "H",
  "chosen_name": "Best (B) + Bivariate Poisson",
  "validation_logloss": 0.9736642193581095,
  "holdout_metrics": {
    "n": 299,
    "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
    "acc_1x2": 0.5016722408026756,
    "brier_1x2": 0.6025146912709042,
    "logloss_1x2": 1.0092004903163196,
    "rps_1x2": 0.43145492397993296,
    "ece_1x2": 0.07845284280936453,
    "brier_btts": 0.24315846591973245,
    "logloss_btts": 0.6798026819389013,
    "acc_btts": 0.5886287625418061,
    "brier_ou25": 0.23552979384615383,
    "logloss_ou25": 0.6629038172370771,
    "acc_ou25": 0.5953177257525084,
    "exact_score_nll": 3.588405315022167,
    "top1_hit": 0.10367892976588629,
    "top3_hit": 0.22742474916387959,
    "top5_hit": 0.3712374581939799,
    "top10_hit": 0.6220735785953178,
    "expected_goal_mae": 1.0558215719063546,
    "expected_goal_rmse": 1.3106910050627907,
    "bootstrap_acc_1x2": {
      "mean": 0.5016722408026756,
      "low": 0.44481605351170567,
      "high": 0.5618729096989966,
      "n": 299
    }
  },
  "validation_metrics": {
    "n": 298,
    "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
    "acc_1x2": 0.5067114093959731,
    "brier_1x2": 0.5780961598322149,
    "logloss_1x2": 0.9736642193581095,
    "rps_1x2": 0.3798372734563758,
    "ece_1x2": 0.06241174496644298,
    "brier_btts": 0.24057874278523492,
    "logloss_btts": 0.6753807287449208,
    "acc_btts": 0.6208053691275168,
    "brier_ou25": 0.23545798879194632,
    "logloss_ou25": 0.6661679111375056,
    "acc_ou25": 0.6342281879194631,
    "exact_score_nll": 3.449135165576437,
    "top1_hit": 0.15771812080536912,
    "top3_hit": 0.31543624161073824,
    "top5_hit": 0.4395973154362416,
    "top10_hit": 0.6644295302013423,
    "expected_goal_mae": 0.9831981543624161,
    "expected_goal_rmse": 1.2449060983630897,
    "bootstrap_acc_1x2": {
      "mean": 0.5067114093959731,
      "low": 0.44966442953020136,
      "high": 0.5671140939597316,
      "n": 298
    }
  },
  "beats_league_baseline_holdout": true,
  "beats_gbgm_v1_holdout": true,
  "league_holdout_logloss": 1.0677728076416662,
  "gbgm_v1_holdout_logloss": 1.1508271697972774
}
```