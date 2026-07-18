# CHALLENGER PHASE 3B — HOLDOUT COMPARISON

Holdout untouched during model selection (validation chose candidate).

```json
{
  "phase3_gbgm1_nm": {
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
  },
  "phase3_league_avg": {
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
  },
  "phase3b_selection": {
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
  },
  "ablation": {
    "full": {
      "val_ll": 1.0111240056024302,
      "hold_ll": 1.0112934479851483
    },
    "remove_elo": {
      "val_ll": 1.0141868426649499,
      "hold_ll": 1.0451902239510036
    },
    "remove_form": {
      "val_ll": 1.0073820768878856,
      "hold_ll": 1.0405637876741756
    },
    "remove_league": {
      "val_ll": 1.0020414637115413,
      "hold_ll": 1.0153794625756742
    },
    "remove_opponent_adj": {
      "val_ll": 1.0105636406110146,
      "hold_ll": 1.0478782103807827
    },
    "remove_home_away_split": {
      "val_ll": 1.0028895828953859,
      "hold_ll": 1.0108532510334074
    }
  },
  "domains": {
    "global": {
      "ok": true,
      "n": 1491,
      "league_ll": 1.0677728076416662,
      "team_ll": 1.0091526576106071,
      "gbgm_v2_ll": 1.0112934479851483
    },
    "premier_league": {
      "ok": true,
      "n": 358,
      "league_ll": 1.0474891213753212,
      "team_ll": 0.9311665346440182,
      "gbgm_v2_ll": 1.0116576634843957
    },
    "bundesliga": {
      "ok": true,
      "n": 1111,
      "league_ll": 1.0876672293725946,
      "team_ll": 1.0240009884845298,
      "gbgm_v2_ll": 1.0161053121568548
    },
    "tier_a_domestic": {
      "ok": true,
      "n": 1469,
      "league_ll": 1.082967662023014,
      "team_ll": 1.0106442261224544,
      "gbgm_v2_ll": 1.0292837732659867
    },
    "international": {
      "ok": false,
      "n": 22,
      "league_ll": null,
      "team_ll": null,
      "gbgm_v2_ll": null
    },
    "high_data": {
      "ok": true,
      "n": 1469,
      "league_ll": 1.082967662023014,
      "team_ll": 1.0106442261224544,
      "gbgm_v2_ll": 1.0292837732659867
    },
    "low_data": {
      "ok": false,
      "n": 22,
      "league_ll": null,
      "team_ll": null,
      "gbgm_v2_ll": null
    }
  }
}
```