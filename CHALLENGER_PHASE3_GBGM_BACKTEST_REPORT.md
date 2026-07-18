# CHALLENGER PHASE 3 — GBGM BACKTEST REPORT

```json
{
  "backends_available": [
    "lightgbm",
    "sklearn_hist"
  ],
  "variants": {
    "NM": {
      "ok": true,
      "manifest": {
        "dataset_version": "challenger-bt-v1",
        "creation_timestamp": "2026-07-18T18:13:29.763446+00:00",
        "competitions": [
          "world_cup_2026",
          "champions_league",
          "premier_league",
          "bundesliga"
        ],
        "fixture_count": 1491,
        "blocked_snapshots": 587,
        "include_market": false,
        "hash": "a1bc4bcefa326e9625f11aedbe0bdbfa9ffe09a97e85e0bf4681585aea92a7f7",
        "leakage_checks": {
          "time_cutoff_kickoff": true,
          "target_fixture_excluded_from_form": true,
          "forbidden_postmatch_fields": true
        },
        "note": "Canonical freezes not used as Challenger training labels; targets are FT scores only after kickoff."
      },
      "split": {
        "method": "expanding_60_20_20",
        "train_n": 894,
        "validation_n": 298,
        "holdout_n": 299,
        "train_end": "2023-12-30T15:00:00",
        "validation_end": "2024-05-04T13:30:00",
        "holdout_end": "2026-07-15T19:00:00"
      },
      "league_avg_holdout": {
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
      "backends": {
        "lightgbm": {
          "validation": {
            "n": 298,
            "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
            "acc_1x2": 0.4597315436241611,
            "brier_1x2": 0.6581696526510071,
            "logloss_1x2": 1.1080302629545489,
            "brier_btts": 0.279298187147651,
            "logloss_btts": 0.7618246603944107,
            "acc_btts": 0.4899328859060403,
            "brier_ou25": 0.27698512332214764,
            "logloss_ou25": 0.7563620334616076,
            "acc_ou25": 0.5134228187919463,
            "top1_hit": 0.09731543624161074,
            "top3_hit": 0.24496644295302014,
            "top5_hit": 0.3523489932885906,
            "top10_hit": 0.6140939597315436,
            "bootstrap_acc_1x2": {
              "mean": 0.4597315436241611,
              "low": 0.40268456375838924,
              "high": 0.5167785234899329,
              "n": 298
            }
          },
          "holdout": {
            "n": 299,
            "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
            "acc_1x2": 0.45484949832775917,
            "brier_1x2": 0.710298501605351,
            "logloss_1x2": 1.2093825318938478,
            "brier_btts": 0.2928290865886288,
            "logloss_btts": 0.7899368557168067,
            "acc_btts": 0.43812709030100333,
            "brier_ou25": 0.25946640719063546,
            "logloss_ou25": 0.7226035676929694,
            "acc_ou25": 0.5585284280936454,
            "top1_hit": 0.06354515050167224,
            "top3_hit": 0.16387959866220736,
            "top5_hit": 0.28762541806020064,
            "top10_hit": 0.5150501672240803,
            "bootstrap_acc_1x2": {
              "mean": 0.45484949832775917,
              "low": 0.4013377926421405,
              "high": 0.5117056856187291,
              "n": 299
            }
          },
          "model_id": "GBGM-1-NM-lightgbm",
          "model_version": "GBGM-1.0.0",
          "metadata": {
            "model_id": "GBGM-1-NM-lightgbm",
            "model_version": "GBGM-1.0.0",
            "target_markets": [
              "1x2",
              "btts",
              "ou25",
              "exact_score"
            ],
            "is_shadow": true,
            "final_decision_authority": false,
            "public_visible": false,
            "variant": "NM",
            "backend": "lightgbm",
            "train_meta": {
              "n": 894,
              "backend": "lightgbm",
              "variant": "NM",
              "feature_cols": [
                "home_goals_for_avg_l5",
                "home_goals_against_avg_l5",
                "away_goals_for_avg_l5",
                "away_goals_against_avg_l5",
                "league_avg_home_goals",
                "league_avg_away_goals",
                "is_home",
                "home_l5_sample",
                "away_l5_sample",
                "league_sample_before_cutoff"
              ],
              "col_medians": [
                1.8,
                1.2,
                1.2,
                1.6666666666666667,
                1.7860262008733625,
                1.3502999869570889,
                1.0,
                5.0,
                5.0,
                297.0
              ],
              "sample_meta": {
                "split": "train",
                "manifest_hash": "a1bc4bcefa326e9625f11aedbe0bdbfa9ffe09a97e85e0bf4681585aea92a7f7"
              },
              "random_seed": 42
            }
          }
        },
        "sklearn_hist": {
          "validation": {
            "n": 298,
            "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
            "acc_1x2": 0.4798657718120805,
            "brier_1x2": 0.6535305469798659,
            "logloss_1x2": 1.092558797596408,
            "brier_btts": 0.2609836637583893,
            "logloss_btts": 0.7202642520830884,
            "acc_btts": 0.5268456375838926,
            "brier_ou25": 0.25783442372483223,
            "logloss_ou25": 0.7119527290338626,
            "acc_ou25": 0.540268456375839,
            "top1_hit": 0.09060402684563758,
            "top3_hit": 0.2483221476510067,
            "top5_hit": 0.3691275167785235,
            "top10_hit": 0.6375838926174496,
            "bootstrap_acc_1x2": {
              "mean": 0.4798657718120805,
              "low": 0.41946308724832215,
              "high": 0.5335570469798657,
              "n": 298
            }
          },
          "holdout": {
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
          "model_id": "GBGM-1-NM-sklearn_hist",
          "model_version": "GBGM-1.0.0",
          "metadata": {
            "model_id": "GBGM-1-NM-sklearn_hist",
            "model_version": "GBGM-1.0.0",
            "target_markets": [
              "1x2",
              "btts",
              "ou25",
              "exact_score"
            ],
            "is_shadow": true,
            "final_decision_authority": false,
            "public_visible": false,
            "variant": "NM",
            "backend": "sklearn_hist",
            "train_meta": {
              "n": 894,
              "backend": "sklearn_hist",
              "variant": "NM",
              "feature_cols": [
                "home_goals_for_avg_l5",
                "home_goals_against_avg_l5",
                "away_goals_for_avg_l5",
                "away_goals_against_avg_l5",
                "league_avg_home_goals",
                "league_avg_away_goals",
                "is_home",
                "home_l5_sample",
                "away_l5_sample",
                "league_sample_before_cutoff"
              ],
              "col_medians": [
                1.8,
                1.2,
                1.2,
                1.6666666666666667,
                1.7860262008733625,
                1.3502999869570889,
                1.0,
                5.0,
                5.0,
                297.0
              ],
              "sample_meta": {
                "split": "train",
                "manifest_hash": "a1bc4bcefa326e9625f11aedbe0bdbfa9ffe09a97e85e0bf4681585aea92a7f7"
              },
              "random_seed": 42
            }
          }
        }
      },
      "selected_backend_by_val_logloss": "sklearn_hist",
      "canonical_note": {
        "frozen_canonical": "FROZEN_CANONICAL",
        "reconstructed_research_only": "RECONSTRUCTED_RESEARCH_ONLY",
        "mixing_rule": "Do not mix reconstructed Challenger metrics with true forward freezes without separate reporting"
      }
    },
    "MC": {
      "ok": true,
      "manifest": {
        "dataset_version": "challenger-bt-v1",
        "creation_timestamp": "2026-07-18T18:13:50.428726+00:00",
        "competitions": [
          "world_cup_2026",
          "champions_league",
          "premier_league",
          "bundesliga"
        ],
        "fixture_count": 1491,
        "blocked_snapshots": 587,
        "include_market": true,
        "hash": "13ecea05276c153576277210be380db26410c45e0afa2a1354c05d39d5a00768",
        "leakage_checks": {
          "time_cutoff_kickoff": true,
          "target_fixture_excluded_from_form": true,
          "forbidden_postmatch_fields": true
        },
        "note": "Canonical freezes not used as Challenger training labels; targets are FT scores only after kickoff."
      },
      "split": {
        "method": "expanding_60_20_20",
        "train_n": 894,
        "validation_n": 298,
        "holdout_n": 299,
        "train_end": "2023-12-30T15:00:00",
        "validation_end": "2024-05-04T13:30:00",
        "holdout_end": "2026-07-15T19:00:00"
      },
      "league_avg_holdout": {
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
      "backends": {
        "lightgbm": {
          "validation": {
            "n": 298,
            "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
            "acc_1x2": 0.4597315436241611,
            "brier_1x2": 0.6581696526510071,
            "logloss_1x2": 1.1080302629545489,
            "brier_btts": 0.279298187147651,
            "logloss_btts": 0.7618246603944107,
            "acc_btts": 0.4899328859060403,
            "brier_ou25": 0.27698512332214764,
            "logloss_ou25": 0.7563620334616076,
            "acc_ou25": 0.5134228187919463,
            "top1_hit": 0.09731543624161074,
            "top3_hit": 0.24496644295302014,
            "top5_hit": 0.3523489932885906,
            "top10_hit": 0.6140939597315436,
            "bootstrap_acc_1x2": {
              "mean": 0.4597315436241611,
              "low": 0.40268456375838924,
              "high": 0.5167785234899329,
              "n": 298
            }
          },
          "holdout": {
            "n": 299,
            "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
            "acc_1x2": 0.45484949832775917,
            "brier_1x2": 0.710298501605351,
            "logloss_1x2": 1.2093825318938478,
            "brier_btts": 0.2928290865886288,
            "logloss_btts": 0.7899368557168067,
            "acc_btts": 0.43812709030100333,
            "brier_ou25": 0.25946640719063546,
            "logloss_ou25": 0.7226035676929694,
            "acc_ou25": 0.5585284280936454,
            "top1_hit": 0.06354515050167224,
            "top3_hit": 0.16387959866220736,
            "top5_hit": 0.28762541806020064,
            "top10_hit": 0.5150501672240803,
            "bootstrap_acc_1x2": {
              "mean": 0.45484949832775917,
              "low": 0.4013377926421405,
              "high": 0.5117056856187291,
              "n": 299
            }
          },
          "model_id": "GBGM-1-MC-lightgbm",
          "model_version": "GBGM-1.0.0",
          "metadata": {
            "model_id": "GBGM-1-MC-lightgbm",
            "model_version": "GBGM-1.0.0",
            "target_markets": [
              "1x2",
              "btts",
              "ou25",
              "exact_score"
            ],
            "is_shadow": true,
            "final_decision_authority": false,
            "public_visible": false,
            "variant": "MC",
            "backend": "lightgbm",
            "train_meta": {
              "n": 894,
              "backend": "lightgbm",
              "variant": "MC",
              "feature_cols": [
                "home_goals_for_avg_l5",
                "home_goals_against_avg_l5",
                "away_goals_for_avg_l5",
                "away_goals_against_avg_l5",
                "league_avg_home_goals",
                "league_avg_away_goals",
                "is_home",
                "home_l5_sample",
                "away_l5_sample",
                "league_sample_before_cutoff",
                "implied_home",
                "implied_draw",
                "implied_away",
                "bookmaker_count",
                "market_odds_usable"
              ],
              "col_medians": [
                1.8,
                1.2,
                1.2,
                1.6666666666666667,
                1.7860262008733625,
                1.3502999869570889,
                1.0,
                5.0,
                5.0,
                297.0,
                null,
                null,
                null,
                null,
                0.0
              ],
              "sample_meta": {
                "split": "train",
                "manifest_hash": "13ecea05276c153576277210be380db26410c45e0afa2a1354c05d39d5a00768"
              },
              "random_seed": 42
            }
          }
        },
        "sklearn_hist": {
          "ok": false,
          "error": "ValueError: window shape cannot be larger than input array shape"
        }
      },
      "selected_backend_by_val_logloss": "lightgbm",
      "canonical_note": {
        "frozen_canonical": "FROZEN_CANONICAL",
        "reconstructed_research_only": "RECONSTRUCTED_RESEARCH_ONLY",
        "mixing_rule": "Do not mix reconstructed Challenger metrics with true forward freezes without separate reporting"
      }
    }
  }
}
```
