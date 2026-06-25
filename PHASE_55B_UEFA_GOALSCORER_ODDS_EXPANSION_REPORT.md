# PHASE 55B — UEFA Goalscorer Odds Expansion

**Date:** 2026-06-24  
**Mode:** Data Expansion → Coverage Growth → Revalidation  
**Status:** Complete — research only  
**API calls:** 0

### Final recommendation: **`ODDS_NOT_ENOUGH`**

---

## Part A — Source inventory

| Source | GS fixtures (est.) |
|--------|-------------------|
| sportmonks_cache_strict | 3 |
| sportmonks_cache_broad | 105 |
| api_football_odds_snapshots | 72 |
| api_football_disk_cache | 72 |
| api_football_raw_cache_walk | 21 |
| shadow_odds_replays | 0 |

Sportmonks strict selections: **703**
Market types (strict): `{'anytime_goalscorer': 417, 'team_goalscorer': 286}`

## Part B — UEFA inventory

| League | Cached | Strict GS | Coverage |
|--------|--------|-----------|----------|
| champions_league | 600 | 0 | 0.0% |
| europa_league | 578 | 3 | 0.5% |
| conference_league | 464 | 0 | 0.0% |

**UEFA strict coverage:** 0.2%
**Bookmakers:** {'bet365': 703}

## Part C — Bridge expansion

| Metric | Value |
|--------|-------|
| WC bridges (54O) | 72 |
| UEFA direct bridges | 3 |
| Merged bridges | 50 |
| UEFA odds selections | 703 |
| Total odds selections | 20644 |

## Part D — Revalidation

| Metric | Before | After | Δ |
|--------|--------|-------|---|
| Fixtures with odds | 47 | 50 | 3 |
| Odds coverage | 3.0% | 3.2% | 0.0019 |
| Overall top-3 | 0.5712 | 0.5712 | 0.0 |
| UEFA top-3 | 0.5658 | 0.5658 | 0.0 |
| Top-1 | 0.2984 | 0.2984 | — |
| Top-5 | 0.7001 | 0.7008 | — |
| MRR | 0.4769 | 0.4769 | — |
| Brier | 0.1372 | 0.1373 | 0.0001 |
| ECE | 0.2515 | 0.2517 | 0.0002 |

## Part E — Impact

| Question | Answer |
|----------|--------|
| UEFA weakness baseline | 0.5658 |
| UEFA after expansion | 0.5658 |
| Gap to WC closed | 0.0 pp (0.0% of gap) |
| Coverage gain | 0.0019 pp |
| WC fixtures with odds | 47 |
| UEFA fixtures with odds | 3 |

### Final recommendation: **`ODDS_NOT_ENOUGH`**

---

## Constraints honored

- No deploy, production, or live prediction changes
