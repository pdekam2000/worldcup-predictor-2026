# PHASE2_FEATURE_EXPANSION_AND_WALK_FORWARD_REPORT

Status: **PHASE2_FEATURE_EXPANSION_AND_WALK_FORWARD_COMPLETE**

## Corpus

- Phase1 usable N: 54
- Phase2 usable N: **223**
- Cohorts: `{'HISTORICAL_PREMATCH_FREEZE': 223}`
- Priced odds: 3 → **209**
- Features available: 22 → **32**

## Walk-forward

- Folds: **12**
- Mean accuracy: 0.6362

## Strategy search

- Strategies tested: **50000**
- Best N≥25: `{'config_hash': '270d57e1962b0d8f', 'accuracy': 0.64, 'n': 25, 'coverage': 0.3906, 'avg_odds': 1.6479, 'roi': 0.0894, 'max_drawdown': -4.7575, 'flags': [], 'config': {'min_confidence': 0, 'min_edge': 0.0, 'max_entropy': None, 'min_top5': 0.65, 'require_agree_ecse': False, 'odds_max': None, 'direction_mode': 'ecse', 'exclude_no_bet': False, 'balanced_only': False}}`
- Best N≥50: `{'config_hash': 'cf3df7912f6076f2', 'accuracy': 0.6038, 'n': 53, 'coverage': 0.8281, 'avg_odds': 1.5139, 'roi': -0.0674, 'max_drawdown': -8.7641, 'flags': [], 'config': {'min_confidence': 0, 'min_edge': 0.4, 'max_entropy': None, 'min_top5': None, 'require_agree_ecse': False, 'odds_max': 2.0, 'direction_mode': 'ecse', 'exclude_no_bet': False, 'balanced_only': False}}`
- Best N≥100: `None`

Phase1 75% @ n=8 remains **SMALL_SAMPLE_NOT_PROMOTABLE**.

## Ablation

- Helped: ['canonical_plus_ecse_agree', 'canonical_plus_conf55', 'canonical_plus_top5', 'canonical_plus_odds_cap', 'ecse_direction']
- Hurt: []

## Error clusters

['underdog_breakout', 'favorite_failure', 'market_contradiction', 'draw_underranked', 'direction_reversal']

## Safety

- NOT DEPLOYED
- CANONICAL UNCHANGED
- WDE UNCHANGED
- ECSE UNCHANGED
- SEALED HOLDOUT UNOPENED
- NO AUTO-PROMOTION
- 75% target **not claimed**
