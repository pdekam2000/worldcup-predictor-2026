# ECSE-1E — Error Analysis Report

**Fixtures:** 168,233

## Common prediction misses (top pairs)

| Predicted | Actual | Count |
|-----------|--------|-------|
| 1-1 | 1-1 | 15665 |
| 1-1 | 1-0 | 13341 |
| 1-1 | 2-1 | 11969 |
| 1-1 | 0-1 | 10639 |
| 1-1 | 1-2 | 9857 |
| 1-1 | 0-0 | 9740 |
| 1-1 | 2-0 | 9338 |
| 1-1 | 2-2 | 7051 |
| 1-1 | 0-2 | 6746 |
| 1-1 | 3-1 | 5742 |
| 1-1 | 3-0 | 5427 |
| 1-1 | 1-3 | 4176 |
| 1-1 | 3-2 | 3827 |
| 1-1 | 0-3 | 3367 |
| 1-1 | 2-3 | 3198 |

## Specific patterns

- Predicted **1-1**, actual **2-1**: 11,969
- Predicted **2-1**, actual **1-1**: 526
- Low-score underestimation (0-0/1-0/0-1 rank>5 or p<5%): **38.7468%** of low-score results (n=38,109)
- High-score overprediction (pred 3+ goals, actual <3): **28.7031%** of 3+ predictions (n=19,632)

## Interpretation

- Independent Poisson tends to concentrate mass on 1-1 / 1-2 / 2-1 corridors.
- Low-scoring results (0-0, 1-0) are systematically under-weighted vs market tails.
- Occasional 3+ goal top picks miss when actual totals stay low.

---

*Read-only evaluation against `historical_fixture_results`.*