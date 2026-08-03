# TRUE_FORWARD_472_COMPLETE_EVALUATION_REPORT

**Status:** `TRUE_FORWARD_472_EVALUATION_PARTIAL_RESULTS_PENDING`
**Program:** `TRUE_FORWARD_472_COMPLETE_EVALUATION_AUDIT`

## Headline

| Question | Answer |
|---|---|
| What is 472? | 472 frozen_predictions rows in forward_prediction_tracking.db; each row is a prematch freeze bundle (WDE+ECSE+BTTS+OU), not one independent fixture evidence unit. 316 unique fixtures; 156 extra rows from multi-freeze snapshots/reuses. |
| Unique fixtures | **316** |
| Finished unique | **168** |
| Evaluated unique | **168** |
| WDE | hits=82 misses=86 n=168 accuracy=48.8% |
| ECSE direction | hits=89 misses=79 n=168 accuracy=53.0% |
| Strict shortlist | hits=0 misses=0 n=0 accuracy=n/a |
| Exact Top1/3/5/10 | 15.5% / 31.5% / 45.2% / None |
| BTTS | 51.8% (n=168) |
| O/U 2.5 | 56.0% (n=168) |
| Best accuracy model | canonical_ecse_direction @ 53.0% (n=168) |
| Best ROI model | canonical_wde_raw_argmax ROI=77.3% (priced_n=3) |
| Gate A/B/C | True / True / False (evaluated unique=168) |
| Any valid >=75% (n>=30) | False |
| Statistical trust | MODERATE |
| Next step | Gate A/B already met on evaluated unique fixtures; continue accumulating until Gate C (≥250). Do not treat raw 472 as evidence. Capture prematch odds on freezes (priced N is currently tiny). Optionally backfill market_evaluations for 26 finished-but-unevaluated freezes via the official evaluator (no prediction regen). |

## Decomposition (472 raw)

```
raw_records = 472
valid_tf_records = 472
unique_fixture_model = 1891
unique_fixture_model_snapshot = 2300
unique_fixtures = 316
finished_unique = 168
evaluated_unique = 168
pending_unresolved = 148
multi_freeze_extra_rows = 156
```

## Fixed rule ea08ac97 (true-forward only)

- Eligible TF: 1
- Finished eligible: 1
- Pending eligible: 0
- Accuracy: 100.0% (n=1)
- ROI: 40.0%
- Historical reference (NOT combined): N=49, 75.5%, ROI=-6.8%

## Snapshot timing

```json
{
  "MID": {
    "n": 49,
    "hits": 24,
    "misses": 25,
    "accuracy": 0.4897959183673469,
    "wilson_95": {
      "low": 0.3557488315940086,
      "high": 0.6253266846659078,
      "center": 0.4905377581299582
    },
    "top5_hit_rate": 0.42857142857142855,
    "avg_odds_home": 1.7733333333333334
  },
  "LATE": {
    "n": 145,
    "hits": 79,
    "misses": 66,
    "accuracy": 0.5448275862068965,
    "wilson_95": {
      "low": 0.463658273260272,
      "high": 0.6236829001751115,
      "center": 0.5436705867176918
    },
    "top5_hit_rate": 0.46206896551724136,
    "avg_odds_home": 0.0
  },
  "FINAL_PREMATCH": {
    "n": 12,
    "hits": 6,
    "misses": 6,
    "accuracy": 0.5,
    "wilson_95": {
      "low": 0.2537781703934222,
      "high": 0.7462218296065778,
      "center": 0.5
    },
    "top5_hit_rate": 0.25,
    "avg_odds_home": 0.0
  },
  "EARLY": {
    "n": 33,
    "hits": 15,
    "misses": 18,
    "accuracy": 0.45454545454545453,
    "wilson_95": {
      "low": 0.298426891258915,
      "high": 0.6201434205625044,
      "center": 0.4592851559107097
    },
    "top5_hit_rate": 0.45454545454545453,
    "avg_odds_home": 0.0
  }
}
```

Paired later-vs-early: {"n_fixtures": 0, "later_better": 0, "later_worse": 0, "same": 0}

## Integrity

```json
{
  "raw_records": 472,
  "valid_records": 472,
  "invalid_issue_instances": 0,
  "post_kickoff_freezes": 0,
  "all_freezes_prematch": true,
  "unique_payload_hashes": 472,
  "issue_counts": {}
}
```

## Safety

- NOT DEPLOYED
- CANONICAL UNCHANGED
- WDE UNCHANGED
- ECSE UNCHANGED
- FREEZES UNCHANGED
- NO PREDICTIONS REGENERATED
- NO AUTO-PROMOTION
- NO RESULT LEAKAGE

## Priced performance (selected)

```json
{
  "canonical_wde_decision": {
    "priced_n": 3,
    "wins": 2,
    "losses": 1,
    "average_odds": 2.2066666666666666,
    "median_odds": 1.87,
    "total_stake": 3.0,
    "total_return": 3.27,
    "net_profit": 0.27,
    "roi": 0.09000000000000001,
    "profit_factor": 1.27,
    "max_drawdown": 1.0,
    "longest_winning_streak": 2,
    "longest_losing_streak": 1
  },
  "canonical_wde_raw_argmax": {
    "priced_n": 3,
    "wins": 3,
    "losses": 0,
    "average_odds": 1.7733333333333334,
    "median_odds": 1.87,
    "total_stake": 3.0,
    "total_return": 5.32,
    "net_profit": 2.3200000000000003,
    "roi": 0.7733333333333334,
    "profit_factor": Infinity,
    "max_drawdown": 0.0,
    "longest_winning_streak": 3,
    "longest_losing_streak": 0
  },
  "canonical_ecse_direction": {
    "priced_n": 3,
    "wins": 2,
    "losses": 1,
    "average_odds": 2.4,
    "median_odds": 2.05,
    "total_stake": 3.0,
    "total_return": 3.4499999999999997,
    "net_profit": 0.44999999999999973,
    "roi": 0.1499999999999999,
    "profit_factor": 1.4499999999999997,
    "max_drawdown": 1.0,
    "longest_winning_streak": 1,
    "longest_losing_streak": 1
  }
}
```
