# TSBP MODEL SPECIFICATION

- model_id: `TSBP-1`
- model_name: Team Strength Bivariate Poisson
- model_family: bivariate_poisson
- model_version: 1.0.0
- distribution: BIVARIATE_POISSON
- status: `FORWARD_SHADOW`
- is_shadow=true · public_visible=false · final_decision_authority=false

## Methods
- Attack: mean goals scored / league mean goals (FT only, before kickoff)
- Defence: mean goals conceded / league mean goals
- Home advantage: league home mean − away mean (embedded in λ)
- Time decay: none (equal-weight expanding history)
- League normalization: per competition_key
- Dependence: bivariate correlation tilt corr=0.05
- Score grid: 0..7 goals, renormalized
- Calibration: none in v1 forward

## Provenance
```json
{
  "model_id": "TSBP-1",
  "model_name": "Team Strength Bivariate Poisson",
  "model_family": "bivariate_poisson",
  "model_version": "1.0.0",
  "distribution": "BIVARIATE_POISSON",
  "status": "FORWARD_SHADOW",
  "is_shadow": true,
  "public_visible": false,
  "final_decision_authority": false,
  "experiment_id": "H",
  "attack_strength_method": "mean_goals_scored / league_mean_goals",
  "defence_strength_method": "mean_goals_conceded / league_mean_goals",
  "home_advantage_method": "league_avg_home_goals - league_avg_away_goals (embedded in \u03bb)",
  "time_decay_policy": "none_equal_weight_expanding",
  "league_normalization_policy": "per_competition",
  "competition_features": "competition_key only (no market features)",
  "parameter_estimation_method": "closed_form_relative_rates_FT_only",
  "draw_dependence_parameter": 0.05,
  "score_grid_truncation": 7,
  "calibration_method": "none_in_v1_forward",
  "domain_policy_version": "tsbp-domain-v1",
  "training_dataset_hash": "phase3b_expanding_train_via_strength_fit",
  "validation_dataset_hash": "phase3b_validation_split",
  "holdout_dataset_hash": "phase3b_holdout_split",
  "holdout_logloss_1x2": 1.0092004903163196,
  "code_commit_sha": "c7d3f5c521672944a42c2d638ad59bb0ccd3f027",
  "model_artifact_hash": "7564f4bff74d3ad42bd312a4e0def684cd17317dbdc4cdbfca72dbff6fe924a9",
  "phase3b_chosen": "H",
  "not_gbgm": true
}
```

Not GBGM. Do not serialize into ECSE fields. All outputs labelled `TSBP_SHADOW`.