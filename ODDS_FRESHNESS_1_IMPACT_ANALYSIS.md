# ODDS-FRESHNESS-1 — Impact Analysis

Evaluated ECSE fixtures: **13**

## Metrics by Freshness Segment

| Segment | n | Top1 | Top3 | Top5 | CS Top1 | BTTS consist | O/U consist | Avg goal err |
|---------|--:|-----:|-----:|-----:|--------:|-------------:|------------:|-------------:|
| FRESH_ODDS | 0 | — | — | — | — | — | — | — |
| STALE_ODDS | 13 | 15.4% | 53.8% | 76.9% | 92.3% | 46.2% | 46.2% | 1.15 |
| ODDS_FRESHNESS_UNKNOWN | 0 | — | — | — | — | — | — | — |
| ODDS_MISSING | 0 | — | — | — | — | — | — | — |

## Key Questions

1. **All evaluated fixtures stale (n=13)** — Top3 53.8%, Top5 76.9%. Cannot compare fresh segment.
2. **Clean-sheet Top1 on stale odds:** 92.3% — elevated clean-sheet bias possible when odds age > threshold.
3. **O/U & BTTS on stale:** O/U consistency 46.2%, BTTS 46.2% (stale segment).

4. **Knockout recommendation:** Require fresh odds (≤6h) before knockout End Result predictions when `requires_fresh_odds=true`. Do not block automatically unless `--strict-fresh-odds` enabled.
