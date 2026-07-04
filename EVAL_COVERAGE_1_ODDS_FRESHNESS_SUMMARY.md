# EVAL-COVERAGE-1 — Odds Freshness Summary

Evaluated ECSE fixtures with 90' results: **0**

## Freshness Counts

| Status | Count |
|--------|------:|
| FRESH_ODDS | 0 |
| STALE_ODDS | 0 |
| ODDS_FRESHNESS_UNKNOWN | 0 |
| REQUIRES_FRESH_ODDS | 0 |

## Questions

1. **How many evaluated matches used stale odds?** **0** / 0
2. **How many used unknown/missing odds metadata?** **0**
3. **Top5 hit rate on stale odds:** None% (0 hits / 0 stale)
4. **Top5 on fresh odds:** 0 hits / 0 fresh (insufficient segment if n=0)

## Recommendation

**Cannot assess odds freshness for End Result research on production** — `ecse_prediction_snapshots` count is **0**; no evaluated ECSE fixtures exist on the canonical DB.

Before ODDS-FRESHNESS-1 or S5 promotion:

1. Backfill ECSE snapshots for finished WC fixtures on production.
2. Re-run EVAL-COVERAGE-1 to establish a real evaluated sample.
3. Then run ODDS-FRESHNESS-1 to segment stale vs fresh odds.

Prior local research (13 matches, all STALE_ODDS) is **not representative of production DB state**.
