# MASSIVE_DATABASE_PROFITABLE_ALGORITHM_REPORT

Status: **MASSIVE_SEARCH_FOUNDATION_AND_100K_COMPLETE**

## Corpus

- DB fixtures: 2979
- Finished results: 2409
- Valid prematch labeled: **225**
- Priced: **209**
- True-forward: 0
- Date range: {'min': '2026-06-12T02:00:00', 'max': '2026-07-29T19:15:00'}
- Split: {'train': 135, 'validation': 45, 'holdout_sealed': 45}

## Search

- Completed: **100000**
- Rate: 6135.1 cfg/s
- Est 1M hours: 0.05 · Est 5M hours: 0.23
- Honest ≥75% candidate: **False**
- Overfit risk: HIGH
- Multiple-testing: WARNING_FDR_REQUIRED_BEFORE_CLAIM

## Best (validation only; holdout sealed)

Accuracy candidate: `{'config_hash': '666e89d9be1e066c', 'validation': {'n': 11, 'hits': 8, 'accuracy': 0.7273, 'ci95': [0.4343, 0.9025], 'coverage': 0.2444, 'priced_n': 11, 'roi': -0.0422, 'max_drawdown': -2.6505, 'avg_odds': 1.3587, 'median_odds': 1.3405, 'net_profit': -0.4643, 'top_league_share': 0.2727, 'extreme_fav_share': 0.2727, 'flags': ['N_LT_50_NOT_DISCOVERY', 'SMALL_SAMPLE']}, 'config': {'market': 'home', 'direction_source': 'wde', 'min_confidence': 0, 'min_edge': 0.0, 'max_entropy': None, 'min_top5': None, 'odds_min': None, 'odds_max': 1.8, 'require_wde_ecse_agree': False, 'require_market_agree': False, 'max_margin': None, 'balanced_only': False, 'exclude_no_bet': False, 'min_lambda_total': 2.0, 'max_lambda_total': None}}`

Profitable candidate: `{'config_hash': '666e89d9be1e066c', 'validation': {'n': 11, 'hits': 8, 'accuracy': 0.7273, 'ci95': [0.4343, 0.9025], 'coverage': 0.2444, 'priced_n': 11, 'roi': -0.0422, 'max_drawdown': -2.6505, 'avg_odds': 1.3587, 'median_odds': 1.3405, 'net_profit': -0.4643, 'top_league_share': 0.2727, 'extreme_fav_share': 0.2727, 'flags': ['N_LT_50_NOT_DISCOVERY', 'SMALL_SAMPLE']}, 'config': {'market': 'home', 'direction_source': 'wde', 'min_confidence': 0, 'min_edge': 0.0, 'max_entropy': None, 'min_top5': None, 'odds_min': None, 'odds_max': 1.8, 'require_wde_ecse_agree': False, 'require_market_agree': False, 'max_margin': None, 'balanced_only': False, 'exclude_no_bet': False, 'min_lambda_total': 2.0, 'max_lambda_total': None}}`

## Resume

```
python scripts/run_massive_algorithm_search_foundation.py --resume --out artifacts/massive_algorithm_search/20260802T193933Z --target 1000000
```

## Safety

- NOT DEPLOYED
- CANONICAL UNCHANGED
- WDE UNCHANGED
- ECSE UNCHANGED
- NO AUTO-PROMOTION
- NO RESULT LEAKAGE
- 75% target **not claimed**
