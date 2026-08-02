# APPROVED_BETS_FORENSIC_EVALUATION_REPORT

Status: **APPROVED_BETS_FORENSIC_EVALUATION_COMPLETE**

## Taxonomy conclusion

No durable APPROVED_BET field; strict cohort = owner/production final shortlist artifacts with no_bet≠true and pre-kickoff integrity.

## Headline — STRICT_COMBINED (production-scope shortlists ∪ owner final shortlists)

| Metric | Value |
|--------|------:|
| Unique approved fixtures | 23 |
| Finished confirmed | 11 |
| Pending/unresolved | 6 |
| Excluded (integrity/no_bet) | 6 |
| 1X2 correct | 5 |
| 1X2 wrong | 6 |
| Accuracy | 0.4545 |
| 95% Wilson CI | [0.2127, 0.7199] |
| Priced N | 6 |
| ROI (unit stake) | 0.29 |
| Max drawdown | -3.0 |

Exact (where TopN frozen on finished overlay): finished=7 · Top1=0 (0.0) · Top3=2 (0.2857) · Top5=3 (0.4286) · Top10=3 (0.4286)

## Cohorts (separate — not mixed into headline)

{
  "STRICT_OWNER_APPROVED": {
    "unique": 23,
    "finished": 14,
    "accuracy": 0.5,
    "roi": 0.29
  },
  "WATCHLIST_ONLY": {
    "unique": 21,
    "finished": 6,
    "accuracy": 0.0,
    "roi": null
  },
  "RESEARCH_APPROVED": {
    "unique": 7,
    "finished": 0,
    "accuracy": null,
    "roi": null
  },
  "EXACT_SCORE_APPROVED": {
    "unique": 6,
    "finished": 0,
    "accuracy": null,
    "roi": null
  },
  "STRICT_PRODUCTION_APPROVED": {
    "unique": 12,
    "finished": 3,
    "accuracy": 0.0,
    "roi": -1.0
  },
  "STRICT_COMBINED_HEADLINE": {
    "unique": 23,
    "finished": 11,
    "accuracy": 0.4545,
    "roi": 0.29
  }
}

## vs all Canonical finished baseline

- Baseline accuracy: 0.5185 (n=54)
- Strict approved accuracy: 0.4545
- Improves?: False
- Sample size sufficient (≥30)?: False

## Segments (strict headline)

Best league row: {'key': 'UEFA Champions League', 'n': 3, 'wins': 1, 'losses': 2, 'accuracy': 0.3333, 'ci95': [0.0615, 0.7923], 'priced_n': 2, 'roi': 0.21, 'avg_odds': 2.37, 'sample_size_warning': True}
Worst league row: {'key': 'UEFA Conference League', 'n': 1, 'wins': 1, 'losses': 0, 'accuracy': 1.0, 'ci95': [0.2065, 1.0], 'priced_n': 1, 'roi': 1.32, 'avg_odds': 2.32, 'sample_size_warning': True}
Best confidence bucket: {'key': '60-64.99', 'n': 2, 'wins': 2, 'losses': 0, 'accuracy': 1.0, 'ci95': [0.3424, 1.0], 'priced_n': 1, 'roi': 1.42, 'avg_odds': 2.42, 'sample_size_warning': True}
Worst confidence bucket: {'key': '55-59.99', 'n': 4, 'wins': 3, 'losses': 1, 'accuracy': 0.75, 'ci95': [0.3006, 0.9544], 'priced_n': 3, 'roi': 0.7733, 'avg_odds': 2.47, 'sample_size_warning': True}

## Biggest approved failures (strict)

[
  {
    "fixture_id": 1585131,
    "match": "France vs Spain",
    "approved_selection": "draw",
    "actual_1x2": "away",
    "final_score": "0-2",
    "confidence": 68.9,
    "odds": 3.2,
    "league": "FIFA World Cup 2026",
    "likely_cause": "DIRECTION_REVERSAL",
    "cohort": "STRICT_COMBINED_HEADLINE"
  },
  {
    "fixture_id": 1556508,
    "match": "Lech Poznan vs Aarhus",
    "approved_selection": "home",
    "actual_1x2": "away",
    "final_score": "0-3",
    "confidence": 67.4,
    "odds": null,
    "league": "UEFA Champions League",
    "likely_cause": "DIRECTION_REVERSAL",
    "cohort": "STRICT_COMBINED_HEADLINE"
  },
  {
    "fixture_id": 1514200,
    "match": "Grotta vs Grindavik",
    "approved_selection": "home",
    "actual_1x2": "away",
    "final_score": "1-2",
    "confidence": 58.5,
    "odds": 2.09,
    "league": "1. Deild",
    "likely_cause": "DIRECTION_REVERSAL",
    "cohort": "STRICT_COMBINED_HEADLINE"
  },
  {
    "fixture_id": 1554376,
    "match": "Drita vs Kauno Žalgiris",
    "approved_selection": "home",
    "actual_1x2": "away",
    "final_score": "2-3",
    "confidence": 54.8,
    "odds": 2.32,
    "league": "UEFA Champions League",
    "likely_cause": "DIRECTION_REVERSAL",
    "cohort": "STRICT_COMBINED_HEADLINE"
  },
  {
    "fixture_id": 1591937,
    "match": "Celje vs Egnatia Rrogozhinë",
    "approved_selection": "away",
    "actual_1x2": "draw",
    "final_score": "1-1",
    "confidence": 44.2,
    "odds": null,
    "league": "champions_league",
    "likely_cause": "DRAW_UNDERRANKED",
    "cohort": "STRICT_COMBINED_HEADLINE"
  },
  {
    "fixture_id": 1589425,
    "match": "Shamrock Rovers vs Ararat-Armenia",
    "approved_selection": "away",
    "actual_1x2": "home",
    "final_score": "2-1",
    "confidence": 44.0,
    "odds": null,
    "league": "champions_league",
    "likely_cause": "DIRECTION_REVERSAL",
    "cohort": "STRICT_COMBINED_HEADLINE"
  }
]

## Reconciliation

{
  "strict_unique": 23,
  "finished_plus_pending_plus_excluded": 23,
  "hits_plus_misses": 11,
  "finished_1x2": 11,
  "exact_rank_sum": 7,
  "exact_finished_n": 7,
  "priced_wins_plus_losses": 6,
  "priced_n": 6,
  "watchlist_in_strict_headline": false,
  "no_bet_true_in_strict_finished": false,
  "approved_despite_no_bet_finished": [
    1514200,
    1514244,
    1554375,
    1554376,
    1554421,
    1556505,
    1586077,
    1589425,
    1591937
  ],
  "invariants_ok": true
}

## Safety

- NOT DEPLOYED
- CANONICAL UNCHANGED
- FREEZES UNCHANGED
- NO PREDICTIONS REGENERATED
